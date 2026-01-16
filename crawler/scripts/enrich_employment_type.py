#!/usr/bin/env python3
"""
employment_type 후처리 배치 스크립트

employment_type이 비어있는 공고의 상세 페이지에서
고용형태 정보를 추출하여 업데이트합니다.
"""

import asyncio
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.firestore import get_db
from app.config import USER_AGENTS
from app.core.proxy_env import get_proxy_url


DETAIL_URL = "https://www.jobkorea.co.kr/Recruit/GI_Read"


def extract_employment_type_from_html(html: str) -> str:
    """HTML에서 고용형태 추출"""
    # 1. JSON에서 employmentType 추출
    emp_match = re.search(r'"employmentType"\s*:\s*"([^"]+)"', html)
    if emp_match:
        emp_code = emp_match.group(1).upper()
        emp_map = {
            "PERMANENT": "정규직",
            "CONTRACT": "계약직",
            "INTERN": "인턴",
            "PARTTIME": "파트타임",
            "DISPATCH": "파견직",
            "FREELANCE": "프리랜서",
        }
        if emp_code in emp_map:
            return emp_map[emp_code]

    # 2. jobTypeName 폴백
    job_type_match = re.search(r'"jobTypeName"\s*:\s*"([^"]+)"', html)
    if job_type_match:
        return job_type_match.group(1)

    # 3. HTML 텍스트에서 직접 추출
    for emp in ["정규직", "계약직", "인턴", "파트타임", "파견직", "프리랜서"]:
        if emp in html:
            return emp

    return ""


async def extract_employment_type(client: httpx.AsyncClient, job_id: str) -> Optional[str]:
    """상세 페이지에서 employment_type 추출"""
    numeric_id = job_id.replace("jk_", "")

    try:
        url = f"{DETAIL_URL}/{numeric_id}"
        response = await client.get(url, timeout=15.0)
        response.raise_for_status()

        return extract_employment_type_from_html(response.text)
    except Exception:
        return None


async def enrich_employment_type(
    limit: int = 5000,
    batch_size: int = 100,
    num_workers: int = 10,
    use_proxy: bool = False
) -> dict:
    """employment_type이 없는 공고 업데이트"""
    db = get_db()
    proxy_url = get_proxy_url() if use_proxy else None

    if use_proxy:
        print(f"[Enrich] 프록시 모드 활성화", flush=True)

    stats = {
        "total": 0,
        "updated": 0,
        "failed": 0,
    }

    print(f"[Enrich] employment_type 후처리 시작", flush=True)
    print(f"[Enrich] 설정: limit={limit}, workers={num_workers}", flush=True)

    # employment_type이 비어있는 공고 조회
    query = db.collection("jobs").where("is_active", "==", True).limit(limit * 2)
    all_docs = list(query.stream())

    target_docs = []
    for doc in all_docs:
        data = doc.to_dict()
        emp_type = data.get("employment_type", "")
        if not emp_type or emp_type.strip() == "":
            target_docs.append(doc)
        if len(target_docs) >= limit:
            break

    stats["total"] = len(target_docs)
    print(f"[Enrich] 처리 대상: {len(target_docs)}건", flush=True)

    if not target_docs:
        print("[Enrich] 처리할 공고 없음", flush=True)
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

            emp_type = await extract_employment_type(client, job_id)

            if emp_type:
                async with updates_lock:
                    updates.append({
                        "ref": doc.reference,
                        "employment_type": emp_type,
                    })

            await asyncio.sleep(0.1)

    # 워커 실행
    print(f"[Enrich] {num_workers}개 워커로 크롤링 시작...", flush=True)
    start_time = asyncio.get_event_loop().time()

    workers = [worker(i) for i in range(num_workers)]
    await asyncio.gather(*workers)

    elapsed = asyncio.get_event_loop().time() - start_time
    print(f"[Enrich] 크롤링 완료: {len(updates)}건 추출 ({elapsed:.1f}초)", flush=True)

    # 배치 업데이트
    now = datetime.now(timezone.utc).isoformat()

    for i in range(0, len(updates), batch_size):
        batch = db.batch()
        batch_updates = updates[i:i+batch_size]

        for update in batch_updates:
            ref = update.pop("ref")
            batch.update(ref, {
                **update,
                "updated_at": now,
            })

        batch.commit()
        stats["updated"] += len(batch_updates)
        print(f"[Enrich] 저장: {stats['updated']}/{len(updates)}건", flush=True)

    stats["failed"] = stats["total"] - stats["updated"]

    # 클라이언트 정리
    for client in clients:
        await client.aclose()

    print(f"\n[Enrich] 완료", flush=True)
    print(f"  - 대상: {stats['total']}건", flush=True)
    print(f"  - 업데이트: {stats['updated']}건", flush=True)
    print(f"  - 실패: {stats['failed']}건", flush=True)

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="employment_type 후처리 배치")
    parser.add_argument("--limit", type=int, default=5000, help="최대 처리 건수")
    parser.add_argument("--workers", type=int, default=10, help="병렬 워커 수")
    parser.add_argument("--proxy", action="store_true", help="프록시 사용")

    args = parser.parse_args()

    asyncio.run(enrich_employment_type(limit=args.limit, num_workers=args.workers, use_proxy=args.proxy))
