#!/usr/bin/env python3
"""
job_keywords 이스케이프 문자 정리 스크립트

job_keywords 필드에서 잘못된 이스케이프 문자(\" 등)를 제거합니다.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.firestore import get_db


def fix_job_keywords(limit: int = 10000, batch_size: int = 500) -> dict:
    """job_keywords 이스케이프 문자 정리"""
    db = get_db()

    stats = {
        "total": 0,
        "fixed": 0,
        "skipped": 0,
    }

    print(f"[Fix] job_keywords 정리 시작")
    print(f"[Fix] 설정: limit={limit}, batch_size={batch_size}")

    # 활성 공고 조회
    query = db.collection("jobs").where("is_active", "==", True).limit(limit)
    all_docs = list(query.stream())

    stats["total"] = len(all_docs)
    print(f"[Fix] 전체 공고: {len(all_docs)}건")

    # 수정이 필요한 공고 필터링
    updates = []
    for doc in all_docs:
        data = doc.to_dict()
        keywords = data.get("job_keywords", [])

        if not keywords:
            continue

        # 이스케이프 문자 정리
        fixed_keywords = []
        needs_fix = False

        for kw in keywords:
            if isinstance(kw, str):
                # 백슬래시, 이스케이프된 따옴표 정리
                cleaned = kw.rstrip("\\").rstrip('"').strip()
                cleaned = cleaned.replace('\\"', '').replace('\\', '')
                if cleaned != kw:
                    needs_fix = True
                if cleaned:
                    fixed_keywords.append(cleaned)
            else:
                fixed_keywords.append(kw)

        if needs_fix:
            updates.append({
                "ref": doc.reference,
                "job_keywords": fixed_keywords,
            })

    print(f"[Fix] 수정 대상: {len(updates)}건")

    if not updates:
        print("[Fix] 수정할 공고 없음")
        return stats

    # 배치 업데이트
    now = datetime.now(timezone.utc).isoformat()

    for i in range(0, len(updates), batch_size):
        batch = db.batch()
        batch_updates = updates[i:i+batch_size]

        for update in batch_updates:
            batch.update(update["ref"], {
                "job_keywords": update["job_keywords"],
                "updated_at": now,
            })

        batch.commit()
        stats["fixed"] += len(batch_updates)
        print(f"[Fix] 저장: {stats['fixed']}/{len(updates)}건")

    stats["skipped"] = stats["total"] - stats["fixed"]

    print(f"\n[Fix] 완료")
    print(f"  - 전체: {stats['total']}건")
    print(f"  - 수정: {stats['fixed']}건")
    print(f"  - 스킵: {stats['skipped']}건")

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="job_keywords 이스케이프 문자 정리")
    parser.add_argument("--limit", type=int, default=10000, help="최대 처리 건수")

    args = parser.parse_args()

    fix_job_keywords(limit=args.limit)
