#!/usr/bin/env python3
"""
company_name 후처리 배치 스크립트

company_name이 없는 공고의 상세 페이지에서 회사명만 추출하여 업데이트합니다.
"""

import asyncio
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.firestore import get_db
from app.config import USER_AGENTS
from app.normalizers.company import CompanyNormalizer


DETAIL_URL = "https://www.jobkorea.co.kr/Recruit/GI_Read"


async def extract_company_name(client: httpx.AsyncClient, job_id: str) -> Optional[str]:
    """상세 페이지에서 company_name만 추출"""
    # job_id에서 숫자만 추출 (jk_12345678 -> 12345678)
    numeric_id = job_id.replace("jk_", "")

    try:
        url = f"{DETAIL_URL}/{numeric_id}"
        response = await client.get(url, timeout=15.0)
        response.raise_for_status()
        html = response.text

        # JSON-LD에서 hiringOrganization.name 추출
        match = re.search(r'"hiringOrganization"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', html)
        if match:
            return match.group(1)

        return None
    except Exception:
        return None


async def enrich_company_name(
    limit: int = 5000,
    batch_size: int = 100,
    num_workers: int = 10
) -> dict:
    """company_name이 없는 공고 업데이트"""
    db = get_db()
    normalizer = CompanyNormalizer()

    stats = {
        "total": 0,
        "updated": 0,
        "failed": 0,
    }

    print(f"[Enrich] company_name 후처리 시작")
    print(f"[Enrich] 설정: limit={limit}, workers={num_workers}")

    # company_name이 없는 공고 조회
    query = db.collection("jobs").where("is_active", "==", True).limit(limit * 2)
    all_docs = list(query.stream())

    # company_name이 없거나 빈 문자열인 공고 필터링
    target_docs = []
    for doc in all_docs:
        data = doc.to_dict()
        company = data.get("company_name", "")
        if not company or company.strip() == "":
            target_docs.append(doc)
        if len(target_docs) >= limit:
            break

    stats["total"] = len(target_docs)
    print(f"[Enrich] 처리 대상: {len(target_docs)}건")

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

            company_name = await extract_company_name(client, job_id)

            if company_name:
                # 정규화
                normalized, company_type = normalizer.normalize(company_name)

                async with updates_lock:
                    updates.append({
                        "ref": doc.reference,
                        "company_name_raw": company_name,
                        "company_name": normalized,
                        "company_type": company_type,
                    })

            await asyncio.sleep(0.1)  # Rate limiting

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
                "company_name_raw": update["company_name_raw"],
                "company_name": update["company_name"],
                "company_type": update["company_type"],
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

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="company_name 후처리 배치")
    parser.add_argument("--limit", type=int, default=5000, help="최대 처리 건수")
    parser.add_argument("--workers", type=int, default=10, help="병렬 워커 수")

    args = parser.parse_args()

    asyncio.run(enrich_company_name(limit=args.limit, num_workers=args.workers))
