#!/usr/bin/env python3
"""
deadline 후처리 배치 스크립트

deadline이 없거나 빈 문자열인 공고의 상세 페이지에서
마감일 정보를 추출하여 업데이트합니다.
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


def extract_deadline_from_html(html: str) -> Dict:
    """HTML에서 마감일 정보 추출"""
    result = {
        "deadline": "",
        "deadline_type": "unknown",
        "deadline_date": None,
    }

    # 1. 날짜 패턴 먼저 시도 (우선순위 높음)
    date_patterns = [
        # Meta description: 마감일 : 2025.04.11
        (r'마감일\s*:\s*(\d{4}\.\d{2}\.\d{2})', "date_dot"),
        # JSON-LD validThrough (한국식)
        (r'"validThrough"\s*:\s*"?(\d{4}\.\d{2}\.\d{2})"?', "date_dot"),
        # JSON-LD validThrough (ISO)
        (r'"validThrough"\s*:\s*"([^"]+)"', "date_iso"),
        # applicationEndAt
        (r'"applicationEndAt"\s*:\s*"([^"]+)"', "date_iso"),
    ]

    for pattern, dtype in date_patterns:
        match = re.search(pattern, html)
        if match:
            date_str = match.group(1).strip()
            try:
                if dtype == "date_dot":
                    # 2025.04.11 형식
                    parsed = datetime.strptime(date_str, "%Y.%m.%d")
                    result["deadline"] = parsed.strftime("%m.%d")
                    result["deadline_date"] = parsed
                    result["deadline_type"] = "date"
                    return result
                elif dtype == "date_iso":
                    if "T" in date_str:
                        parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00").split("+")[0])
                    elif "-" in date_str:
                        parsed = datetime.strptime(date_str[:10], "%Y-%m-%d")
                    else:
                        continue
                    result["deadline"] = parsed.strftime("%m.%d")
                    result["deadline_date"] = parsed
                    result["deadline_type"] = "date"
                    return result
            except:
                pass

    # 2. 상시채용/채용시마감 패턴
    ongoing_patterns = [
        (r'상시\s*채용|상시채용', "ongoing"),
        (r'채용\s*시\s*마감|채용시까지', "until_hired"),
    ]

    for pattern, dtype in ongoing_patterns:
        if re.search(pattern, html, re.IGNORECASE):
            if dtype == "ongoing":
                result["deadline"] = "상시채용"
                result["deadline_type"] = "ongoing"
            else:
                result["deadline"] = "채용시 마감"
                result["deadline_type"] = "until_hired"
            return result

    # 3. 아무것도 없으면 unknown
    result["deadline"] = ""
    result["deadline_type"] = "unknown"
    return result


async def extract_deadline(client: httpx.AsyncClient, job_id: str) -> Optional[Dict]:
    """상세 페이지에서 deadline 추출"""
    numeric_id = job_id.replace("jk_", "")

    try:
        url = f"{DETAIL_URL}/{numeric_id}"
        response = await client.get(url, timeout=15.0)
        response.raise_for_status()

        return extract_deadline_from_html(response.text)
    except Exception:
        return None


async def enrich_deadline(
    limit: int = 5000,
    batch_size: int = 100,
    num_workers: int = 10,
    use_proxy: bool = False
) -> dict:
    """deadline이 없는 공고 업데이트"""
    db = get_db()
    proxy_url = get_proxy_url() if use_proxy else None

    if use_proxy:
        print(f"[Enrich] 프록시 모드 활성화")

    stats = {
        "total": 0,
        "updated": 0,
        "failed": 0,
    }

    print(f"[Enrich] deadline 후처리 시작")
    print(f"[Enrich] 설정: limit={limit}, workers={num_workers}")

    # 모든 활성 공고 조회 (상시채용으로 잘못 설정된 것도 다시 확인)
    query = db.collection("jobs").where("is_active", "==", True).limit(limit)
    target_docs = list(query.stream())

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

            deadline_info = await extract_deadline(client, job_id)

            if deadline_info and deadline_info.get("deadline"):
                async with updates_lock:
                    updates.append({
                        "ref": doc.reference,
                        **deadline_info,
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
            ref = update.pop("ref")
            batch.update(ref, {
                **update,
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

    parser = argparse.ArgumentParser(description="deadline 후처리 배치")
    parser.add_argument("--limit", type=int, default=5000, help="최대 처리 건수")
    parser.add_argument("--workers", type=int, default=10, help="병렬 워커 수")
    parser.add_argument("--proxy", action="store_true", help="프록시 사용")

    args = parser.parse_args()

    asyncio.run(enrich_deadline(limit=args.limit, num_workers=args.workers, use_proxy=args.proxy))
