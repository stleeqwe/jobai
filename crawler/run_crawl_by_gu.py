#!/usr/bin/env python3
"""V2 크롤러 - 구별 병렬 크롤링 (API 250페이지 제한 우회)

강남구(16,000+건)는 jobtype+career 조합으로 분할하여 전수 수집
"""

import asyncio
import sys
import os
from datetime import datetime
from typing import Set, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.scrapers.jobkorea_v2 import JobKoreaScraperV2
from app.core.ajax_client import AdaptiveRateLimiter
from app.db.firestore import save_jobs, get_job_stats, save_crawl_log
from app.logging_config import get_logger

logger = get_logger("crawler.gu")

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

# 강남구 분할 쿼리 (10,000건 초과 대응)
GANGNAM_SPLIT_QUERIES = [
    {"name": "정규직+신입", "jobtype": "1", "career": "1"},
    {"name": "정규직+경력", "jobtype": "1", "career": "2"},
    {"name": "정규직+경력무관", "jobtype": "1", "career": "3"},
    {"name": "계약직", "jobtype": "2"},
    {"name": "파견직", "jobtype": "3"},
    {"name": "위촉직", "jobtype": "4"},
    {"name": "인턴", "jobtype": "5"},
    {"name": "아르바이트", "jobtype": "10"},
]


async def crawl_gu(gu_name: str, gu_code: str, all_ids: Set[str]) -> int:
    """단일 구 크롤링 (강남구는 분할 처리)"""
    import re

    # 강남구는 분할 크롤링 (10,000건 초과 대응)
    if gu_code == "I010":
        return await crawl_gangnam_split(gu_code, all_ids)

    scraper = JobKoreaScraperV2(num_workers=5, use_proxy=False, fallback_to_proxy=True)

    try:
        await scraper.initialize()

        # 해당 구의 총 공고 수 확인
        resp = await scraper.clients[0].get(
            "https://www.jobkorea.co.kr/Recruit/Home/_GI_List",
            params={"Page": 1, "local": gu_code},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        match = re.search(r'hdnGICnt.*?value="([\d,]+)"', resp.text)
        total_count = int(match.group(1).replace(",", "")) if match else 0

        if total_count == 0:
            print(f"[{gu_name}] 공고 없음, 건너뜀")
            return 0

        max_pages = min(250, (total_count // 40) + 1)
        print(f"[{gu_name}] {total_count:,}건 ({max_pages}페이지)")

        # 목록 수집 (local 파라미터 지정)
        collected_ids = await crawl_list_with_params(scraper, {"local": gu_code}, max_pages)

        before_count = len(all_ids)
        all_ids.update(collected_ids)
        new_count = len(all_ids) - before_count

        print(f"[{gu_name}] 완료: {len(collected_ids)}개 수집, {new_count}개 신규")

        return len(collected_ids)

    finally:
        await scraper.close()


async def crawl_gangnam_split(gu_code: str, all_ids: Set[str]) -> int:
    """강남구 분할 크롤링 (jobtype+career 조합)"""
    import re

    print(f"[강남구] 분할 크롤링 시작 (10,000건 초과 대응)")

    scraper = JobKoreaScraperV2(num_workers=5, use_proxy=False, fallback_to_proxy=True)
    total_collected = 0

    try:
        await scraper.initialize()

        for query in GANGNAM_SPLIT_QUERIES:
            params = {"local": gu_code}
            if "jobtype" in query:
                params["jobtype"] = query["jobtype"]
            if "career" in query:
                params["career"] = query["career"]

            # 해당 쿼리의 공고 수 확인
            resp = await scraper.clients[0].get(
                "https://www.jobkorea.co.kr/Recruit/Home/_GI_List",
                params={"Page": 1, **params},
                headers={"X-Requested-With": "XMLHttpRequest"}
            )
            match = re.search(r'hdnGICnt.*?value="([\d,]+)"', resp.text)
            count = int(match.group(1).replace(",", "")) if match else 0

            if count == 0:
                print(f"  [{query['name']}] 공고 없음, 건너뜀")
                continue

            max_pages = min(250, (count // 40) + 1)
            print(f"  [{query['name']}] {count:,}건 ({max_pages}페이지)")

            # 목록 수집
            collected_ids = await crawl_list_with_params(scraper, params, max_pages)

            before_count = len(all_ids)
            all_ids.update(collected_ids)
            new_count = len(all_ids) - before_count

            print(f"  [{query['name']}] 완료: {len(collected_ids)}개, 신규 {new_count}개")
            total_collected += len(collected_ids)

            await asyncio.sleep(0.5)  # 쿼리 간 간격

        print(f"[강남구] 분할 크롤링 완료: 총 {total_collected:,}개 (중복 제거 후 {len(all_ids):,}개)")
        return total_collected

    finally:
        await scraper.close()


async def crawl_list_with_params(scraper: JobKoreaScraperV2, params: Dict, max_pages: int) -> Set[str]:
    """파라미터로 목록 수집 (local, jobtype, career 등)"""
    import re
    collected_ids: Set[str] = set()
    rate_limiter = AdaptiveRateLimiter()
    no_new_pages = 0
    repeat_pages = 0
    last_page_ids: Optional[Set[str]] = None

    for page in range(1, max_pages + 1):
        try:
            client = scraper.clients[page % len(scraper.clients)]
            resp = await client.get(
                "https://www.jobkorea.co.kr/Recruit/Home/_GI_List",
                params={"Page": page, **params},
                headers={"X-Requested-With": "XMLHttpRequest"}
            )

            if resp.status_code == 200:
                page_ids = set(re.findall(r'GI_Read/(\d+)', resp.text))
                new_ids = page_ids - collected_ids
                collected_ids.update(page_ids)

                if not new_ids:
                    no_new_pages += 1
                else:
                    no_new_pages = 0

                if last_page_ids is not None and page_ids == last_page_ids:
                    repeat_pages += 1
                else:
                    repeat_pages = 0
                last_page_ids = page_ids

                if repeat_pages >= 2 or no_new_pages >= 3:
                    logger.warning(f"중복 페이지 감지로 조기 종료: 페이지 {page}")
                    break

                rate_limiter.on_success()
            else:
                logger.warning(f"AJAX 호출 실패: 페이지 {page}, 상태 {resp.status_code}")
                rate_limiter.on_error(resp.status_code)

            if page % 50 == 0:
                print(f"    페이지 {page}/{max_pages}: 누적 {len(collected_ids)}개")

            await asyncio.sleep(rate_limiter.get_delay())

        except Exception as e:
            logger.warning(f"페이지 {page} 실패: {e}")
            await asyncio.sleep(rate_limiter.get_delay())

    return collected_ids


async def run_crawl_by_gu():
    """구별 병렬 크롤링"""
    start_time = datetime.now()

    print("=" * 70)
    print("V2 구별 크롤링 (API 250페이지 제한 우회)")
    print(f"시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # DB 상태
    stats_before = await get_job_stats()
    print(f"\n[DB] 현재: {stats_before['total_jobs']:,}건")

    # 전체 ID 수집
    all_ids: Set[str] = set()
    gu_stats: Dict[str, int] = {}

    # 구별 순차 크롤링 (병렬은 차단 위험)
    for gu_name, gu_code in SEOUL_GU_CODES.items():
        try:
            count = await crawl_gu(gu_name, gu_code, all_ids)
            gu_stats[gu_name] = count
            print(f"[진행] 전체 고유 ID: {len(all_ids):,}개\n")
        except Exception as e:
            print(f"[{gu_name}] 오류: {e}")
            gu_stats[gu_name] = 0

    print("=" * 70)
    print(f"목록 수집 완료: {len(all_ids):,}개 고유 ID")
    print("=" * 70)

    # 상세 수집
    if all_ids:
        print(f"\n상세 수집 시작: {len(all_ids):,}건")

        scraper = JobKoreaScraperV2(
            num_workers=10,
            use_proxy=True,
            fallback_to_proxy=True,
            proxy_pool_size=10,
            proxy_start_pool=True,
            proxy_pool_warmup=True,
            proxy_worker_rotate_threshold=2,
            proxy_session_lifetime="30m",
            proxy_speed_threshold=2.0,
            proxy_delay_threshold=1.0,
            proxy_speed_consecutive=3,
            proxy_speed_warmup=500,
        )
        try:
            await scraper.initialize()
            scraper.rate_limiter.min_delay = 0.2
            scraper.rate_limiter.delay = 0.2
            success, save_stats = await scraper.crawl_details(
                all_ids,
                save_callback=save_jobs,
                batch_size=500,
                parallel_batch=6,
                retry_limit=3,
                retry_backoff=1.5,
                min_parallel_batch=3,
            )
        finally:
            await scraper.close()

        end_time = datetime.now()
        elapsed = (end_time - start_time).total_seconds()

        print("\n" + "=" * 70)
        print("완료!")
        print(f"  - 고유 ID: {len(all_ids):,}개")
        print(f"  - 상세 성공: {success:,}건")
        print(f"  - 신규: {save_stats.get('new', 0):,}건")
        print(f"  - 업데이트: {save_stats.get('updated', 0):,}건")
        print(f"  - 소요: {elapsed/60:.1f}분")

        # DB 상태
        stats_after = await get_job_stats()
        print(f"\n[DB] 결과: {stats_after['total_jobs']:,}건 (+{stats_after['total_jobs'] - stats_before['total_jobs']:,})")

        # 로그 저장
        await save_crawl_log({
            "started_at": start_time.isoformat(),
            "finished_at": end_time.isoformat(),
            "elapsed_seconds": int(elapsed),
            "total_ids": len(all_ids),
            "success": success,
            "new": save_stats.get("new", 0),
            "updated": save_stats.get("updated", 0),
            "version": "v2-gu",
            "gu_stats": gu_stats,
        })


if __name__ == "__main__":
    asyncio.run(run_crawl_by_gu())
