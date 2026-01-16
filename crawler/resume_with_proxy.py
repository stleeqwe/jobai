#!/usr/bin/env python3
"""프록시 10워커로 남은 크롤링 재개

이전 크롤링에서 수집된 ID 목록을 기반으로
DB에 없는 공고만 프록시로 수집
"""

import asyncio
import re
import sys
import os
from datetime import datetime
from typing import Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.scrapers.jobkorea_v2 import JobKoreaScraperV2
from app.core.proxy_env import get_proxy_url
from app.db.firestore import save_jobs, get_job_stats
from app.logging_config import get_logger
from app.config import USER_AGENTS
import httpx

logger = get_logger("crawler.proxy")

# 서울시 25개 구 코드
SEOUL_GU_CODES = {
    "강남구": "I010", "서초구": "I020", "송파구": "I030", "강동구": "I040",
    "마포구": "I050", "영등포구": "I060", "용산구": "I070", "종로구": "I080",
    "중구": "I090", "성동구": "I100", "광진구": "I110", "동대문구": "I120",
    "중랑구": "I130", "성북구": "I140", "강북구": "I150", "도봉구": "I160",
    "노원구": "I170", "은평구": "I180", "서대문구": "I190", "양천구": "I200",
    "강서구": "I210", "구로구": "I220", "금천구": "I230", "동작구": "I240",
    "관악구": "I250",
}


class ProxyWorkerPool:
    """10개 고정 IP 프록시 워커 풀"""

    def __init__(self, num_workers: int = 10):
        self.num_workers = num_workers
        self.clients: list[httpx.AsyncClient] = []
        self.cookies: httpx.Cookies = None

    def _get_proxy_url(self, worker_id: int) -> str:
        """워커별 Sticky 세션 프록시 URL"""
        session_id = f"worker{worker_id:02d}"
        return get_proxy_url(session_id=session_id, lifetime="30m")

    async def initialize(self):
        """10개 워커 초기화 (각각 다른 IP)"""
        print(f"프록시 워커 {self.num_workers}개 초기화 중...")

        # 먼저 쿠키 획득 (프록시 없이)
        init_client = httpx.AsyncClient(timeout=30.0)
        resp = await init_client.get(
            "https://www.jobkorea.co.kr/recruit/joblist",
            params={"menucode": "local", "local": "I000"}
        )
        self.cookies = init_client.cookies
        await init_client.aclose()

        # 각 워커에 다른 Sticky IP 할당
        for i in range(self.num_workers):
            proxy_url = self._get_proxy_url(i)
            client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": USER_AGENTS[i % len(USER_AGENTS)],
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "ko-KR,ko;q=0.9",
                },
                follow_redirects=True,
                proxy=proxy_url,
                cookies=self.cookies,
            )
            self.clients.append(client)

        # IP 확인
        print("워커 IP 확인:")
        for i, client in enumerate(self.clients[:3]):  # 처음 3개만 확인
            try:
                resp = await client.get("https://api.ipify.org", timeout=10.0)
                print(f"  Worker {i}: {resp.text}")
            except:
                print(f"  Worker {i}: IP 확인 실패")

        print(f"✅ {self.num_workers}개 워커 준비 완료")

    async def close(self):
        for client in self.clients:
            await client.aclose()
        self.clients = []


async def collect_all_ids() -> Set[str]:
    """전체 공고 ID 빠르게 수집 (목록만)"""
    print("\n[Phase 1] 전체 ID 목록 수집")

    all_ids: Set[str] = set()

    # 프록시 없이 빠르게 목록만 수집
    client = httpx.AsyncClient(timeout=30.0)

    try:
        # 서울 전체 (I000)에서 최대한 수집
        for page in range(1, 251):  # 250페이지 = 10,000건
            resp = await client.get(
                "https://www.jobkorea.co.kr/Recruit/Home/_GI_List",
                params={"Page": page, "local": "I000"},
                headers={"X-Requested-With": "XMLHttpRequest"}
            )

            if resp.status_code == 200:
                matches = re.findall(r'GI_Read/(\d+)', resp.text)
                all_ids.update(matches)

            if page % 50 == 0:
                print(f"  페이지 {page}/250: {len(all_ids):,}개")

            await asyncio.sleep(0.03)

        # 구별로 추가 수집 (중복 제거됨)
        for gu_name, gu_code in list(SEOUL_GU_CODES.items())[:5]:  # 상위 5개 구만
            for page in range(1, 101):  # 각 구 100페이지
                resp = await client.get(
                    "https://www.jobkorea.co.kr/Recruit/Home/_GI_List",
                    params={"Page": page, "local": gu_code},
                    headers={"X-Requested-With": "XMLHttpRequest"}
                )

                if resp.status_code == 200:
                    matches = re.findall(r'GI_Read/(\d+)', resp.text)
                    all_ids.update(matches)

                await asyncio.sleep(0.03)

            print(f"  {gu_name} 완료: 누적 {len(all_ids):,}개")

    finally:
        await client.aclose()

    print(f"\n총 {len(all_ids):,}개 ID 수집")
    return all_ids


async def get_existing_ids() -> Set[str]:
    """DB에 이미 있는 공고 ID 조회"""
    print("\n[Phase 2] DB 기존 ID 조회")

    from app.db.firestore import get_db
    db = get_db()

    existing_ids: Set[str] = set()

    # 동기 Firestore 클라이언트 사용 - document ID만 조회
    # DB ID는 "jk_12345" 형식, 수집 ID는 "12345" 형식
    for doc in db.collection("jobs").select([]).stream():
        # jk_ prefix 제거해서 비교
        raw_id = doc.id.replace("jk_", "") if doc.id.startswith("jk_") else doc.id
        existing_ids.add(raw_id)

    print(f"DB 기존 ID: {len(existing_ids):,}개")
    return existing_ids


async def crawl_details_with_proxy(job_ids: Set[str], pool: ProxyWorkerPool):
    """프록시 워커로 상세 페이지 병렬 수집"""
    print(f"\n[Phase 3] 프록시로 상세 수집: {len(job_ids):,}건")

    from app.scrapers.jobkorea_v2 import JobKoreaScraperV2
    from bs4 import BeautifulSoup

    # 스크래퍼 생성 (파싱 로직만 사용)
    scraper = JobKoreaScraperV2(num_workers=1)
    scraper.clients = pool.clients  # 프록시 클라이언트 사용

    job_ids_list = list(job_ids)
    total = len(job_ids_list)
    results = []
    failed = 0
    start_time = datetime.now()

    # 배치 처리
    batch_size = 500

    for batch_start in range(0, total, batch_size):
        batch = job_ids_list[batch_start:batch_start + batch_size]
        batch_results = []

        # 세마포어로 동시 요청 제한
        semaphore = asyncio.Semaphore(pool.num_workers * 2)

        async def fetch_one(job_id: str, worker_id: int):
            nonlocal failed
            async with semaphore:
                try:
                    client = pool.clients[worker_id % len(pool.clients)]
                    url = f"https://www.jobkorea.co.kr/Recruit/GI_Read/{job_id}"

                    resp = await client.get(url, timeout=15.0)

                    if resp.status_code == 200:
                        # 인자 순서: job_id, html
                        job_data = scraper._parse_detail_page(job_id, resp.text)
                        if job_data.get("title"):
                            return job_data

                    failed += 1
                    return None

                except Exception as e:
                    failed += 1
                    return None

        # 배치 내 병렬 처리
        tasks = [
            fetch_one(job_id, i)
            for i, job_id in enumerate(batch)
        ]
        batch_results = await asyncio.gather(*tasks)

        # None 제거
        valid_results = [r for r in batch_results if r]

        # DB 저장
        if valid_results:
            save_result = await save_jobs(valid_results)
            results.extend(valid_results)

        # 진행률 출력
        elapsed = (datetime.now() - start_time).total_seconds()
        done = batch_start + len(batch)
        speed = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / speed / 60 if speed > 0 else 0

        print(f"[V2] 진행: {done:,}/{total:,} ({speed:.1f}건/s, ETA: {eta:.1f}분)")
        print(f"[V2] 저장: {len(valid_results)}건, 실패: {failed}")

    return len(results)


async def main():
    start_time = datetime.now()

    print("=" * 70)
    print("프록시 10워커 크롤링 재개")
    print(f"시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # DB 상태
    stats_before = await get_job_stats()
    print(f"\n[DB] 현재: {stats_before['total_jobs']:,}건")

    # 1. 전체 ID 수집
    all_ids = await collect_all_ids()

    # 2. DB 기존 ID 조회
    existing_ids = await get_existing_ids()

    # 3. 미수집 ID 계산
    missing_ids = all_ids - existing_ids
    print(f"\n미수집 ID: {len(missing_ids):,}건")

    if not missing_ids:
        print("모든 공고가 이미 수집됨!")
        return

    # 4. 프록시 워커 풀 초기화
    pool = ProxyWorkerPool(num_workers=10)
    await pool.initialize()

    try:
        # 5. 프록시로 상세 수집
        success = await crawl_details_with_proxy(missing_ids, pool)

        end_time = datetime.now()
        elapsed = (end_time - start_time).total_seconds()

        print("\n" + "=" * 70)
        print("완료!")
        print(f"  - 미수집 ID: {len(missing_ids):,}개")
        print(f"  - 수집 성공: {success:,}건")
        print(f"  - 소요: {elapsed/60:.1f}분")
        print(f"  - 속도: {success/elapsed:.1f}건/s")

        # DB 상태
        stats_after = await get_job_stats()
        print(f"\n[DB] 결과: {stats_after['total_jobs']:,}건 (+{stats_after['total_jobs'] - stats_before['total_jobs']:,})")

    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
