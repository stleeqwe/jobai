#!/usr/bin/env python3
"""
title 후처리 배치 스크립트

"회사명 채용" 패턴의 잘못된 title을 가진 공고의 상세 페이지에서
올바른 title을 추출하여 업데이트합니다.
"""

import asyncio
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.firestore import get_db
from app.config import USER_AGENTS
from app.core.proxy_env import get_proxy_url


DETAIL_URL = "https://www.jobkorea.co.kr/Recruit/GI_Read"


def is_bad_title(title: str, company_name: str) -> bool:
    """잘못된 title 패턴인지 확인"""
    if not title or not company_name:
        return True

    title = title.strip()

    # 1. 잘린 제목 (.., ... 로 끝남)
    if title.endswith("..") or title.endswith("..."):
        return True

    # 2. "회사명 채용" 패턴 (정확히 일치)
    if title == f"{company_name} 채용":
        return True
    if title == f"{company_name} 채용...":
        return True

    # 3. (주), ㈜, 주식회사 등이 붙은 회사명 패턴
    # 예: "(주)푸드테크 채용", "㈜케이세웅건설 채용"
    # 단, "(주)푸드테크 전략기획 채용" 처럼 직무가 포함된 경우는 허용
    company_patterns = [
        f"(주){company_name}",
        f"㈜{company_name}",
        f"주식회사 {company_name}",
        f"주식회사{company_name}",
        f"{company_name}(주)",
        f"{company_name}㈜",
    ]
    for cp in company_patterns:
        # 정확히 "회사명 채용"만 bad
        if title == f"{cp} 채용":
            return True
        # 직무 없이 "채용"으로 끝나는 짧은 제목만 bad (임계값: +5)
        if title.startswith(cp) and title.endswith("채용") and len(title) <= len(cp) + 5:
            return True

    # 4. 회사명으로 시작하고 "채용"으로 끝나는 짧은 title (임계값: +5)
    if title.startswith(company_name) and title.endswith("채용") and len(title) <= len(company_name) + 5:
        return True

    # 5. 너무 짧은 title
    if len(title) < 10:
        return True

    return False


def extract_title_from_html(html: str) -> Optional[str]:
    """HTML에서 올바른 title 추출"""
    soup = BeautifulSoup(html, "lxml")

    # 1. JSON-LD의 title 필드
    json_ld_title = re.search(r'"@type"\s*:\s*"JobPosting"[^}]*"title"\s*:\s*"([^"]+)"', html, re.DOTALL)
    if not json_ld_title:
        json_ld_title = re.search(r'"title"\s*:\s*"([^"]{10,})"', html)
    if json_ld_title:
        return json_ld_title.group(1)

    # 2. CSS 셀렉터
    title_el = soup.select_one("h1.title, .tit_job, .job-title, .recruit-title")
    if title_el:
        text = title_el.get_text(strip=True)
        if len(text) >= 10:
            return text

    # 3. og:title
    og_title = soup.select_one('meta[property="og:title"]')
    if og_title:
        content = og_title.get("content", "")
        if len(content) >= 10:
            return content

    return None


async def extract_title(client: httpx.AsyncClient, job_id: str) -> Optional[str]:
    """상세 페이지에서 title 추출"""
    numeric_id = job_id.replace("jk_", "")

    try:
        url = f"{DETAIL_URL}/{numeric_id}"
        response = await client.get(url, timeout=15.0)
        response.raise_for_status()

        return extract_title_from_html(response.text)
    except Exception:
        return None


async def enrich_title(
    limit: int = 5000,
    batch_size: int = 100,
    num_workers: int = 10,
    use_proxy: bool = False
) -> dict:
    """잘못된 title을 가진 공고 업데이트"""
    db = get_db()
    proxy_url = get_proxy_url() if use_proxy else None

    if use_proxy:
        print(f"[Enrich] 프록시 모드 활성화")

    stats = {
        "total": 0,
        "updated": 0,
        "failed": 0,
        "skipped": 0,
    }

    print(f"[Enrich] title 후처리 시작")
    print(f"[Enrich] 설정: limit={limit}, workers={num_workers}")

    # 활성 공고 조회
    query = db.collection("jobs").where("is_active", "==", True).limit(limit * 2)
    all_docs = list(query.stream())

    # 잘못된 title 패턴 필터링
    target_docs = []
    for doc in all_docs:
        data = doc.to_dict()
        title = data.get("title", "")
        company = data.get("company_name", "")

        if is_bad_title(title, company):
            target_docs.append(doc)

        if len(target_docs) >= limit:
            break

    stats["total"] = len(target_docs)
    print(f"[Enrich] 처리 대상 (잘못된 title): {len(target_docs)}건")

    if not target_docs:
        print("[Enrich] 처리할 공고 없음")
        return stats

    # HTTP 클라이언트 풀 생성
    clients = []
    for i in range(num_workers):
        client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": USER_AGENTS[i % len(USER_AGENTS)],
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ko-KR,ko;q=0.9",
            },
            follow_redirects=True,
            proxy=proxy_url,
        )
        clients.append(client)

    # 작업 큐
    queue = asyncio.Queue()
    for doc in target_docs:
        await queue.put(doc)

    # 결과 저장용
    updates = []
    updates_lock = asyncio.Lock()

    async def worker(worker_id: int):
        client = clients[worker_id]

        while True:
            try:
                doc = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            data = doc.to_dict()
            job_id = data.get("id", "")
            old_title = data.get("title", "")

            new_title = await extract_title(client, job_id)

            if new_title and new_title != old_title and len(new_title) >= 10:
                async with updates_lock:
                    updates.append({
                        "ref": doc.reference,
                        "title": new_title,
                        "old_title": old_title,
                    })

            await asyncio.sleep(0.1)

    # 워커 실행
    print(f"[Enrich] {num_workers}개 워커로 크롤링 시작...")
    start_time = asyncio.get_event_loop().time()

    workers = [worker(i) for i in range(num_workers)]
    await asyncio.gather(*workers)

    elapsed = asyncio.get_event_loop().time() - start_time
    print(f"[Enrich] 크롤링 완료: {len(updates)}건 추출 ({elapsed:.1f}초)")

    # 배치 업데이트
    now = datetime.now(timezone.utc).isoformat()

    for i in range(0, len(updates), batch_size):
        batch = db.batch()
        batch_updates = updates[i:i+batch_size]

        for update in batch_updates:
            batch.update(update["ref"], {
                "title": update["title"],
                "updated_at": now,
            })

        batch.commit()
        stats["updated"] += len(batch_updates)
        print(f"[Enrich] 저장: {stats['updated']}/{len(updates)}건")

    stats["failed"] = stats["total"] - stats["updated"]

    # 클라이언트 정리
    for client in clients:
        await client.aclose()

    print(f"\n[Enrich] 완료")
    print(f"  - 대상: {stats['total']}건")
    print(f"  - 업데이트: {stats['updated']}건")
    print(f"  - 실패: {stats['failed']}건")

    # 샘플 출력
    if updates:
        print("\n샘플 변경:")
        for u in updates[:5]:
            old = u['old_title']
            new = u['title']
            print(f"  - \"{old}\" → \"{new}\"")

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="title 후처리 배치")
    parser.add_argument("--limit", type=int, default=5000, help="최대 처리 건수")
    parser.add_argument("--workers", type=int, default=10, help="병렬 워커 수")
    parser.add_argument("--proxy", action="store_true", help="프록시 사용")

    args = parser.parse_args()

    asyncio.run(enrich_title(limit=args.limit, num_workers=args.workers, use_proxy=args.proxy))
