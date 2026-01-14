#!/usr/bin/env python3
"""
nearest_station 후처리 배치 스크립트

크롤링 후 nearest_station이 없는 공고에 대해 가장 가까운 지하철역을 계산합니다.
크롤링과 분리하여 실행 → 크롤링 속도 최적화

사용법:
    python scripts/enrich_nearest_station.py [--limit 1000] [--batch-size 100]
"""

import asyncio
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.firestore import get_db
from app.services.seoul_subway_commute import SeoulSubwayCommute
from app.config import settings


async def enrich_nearest_station(
    limit: int = 1000,
    batch_size: int = 100,
    force: bool = False
) -> dict:
    """
    nearest_station이 없는 공고에 지하철역 정보 추가

    Args:
        limit: 최대 처리 건수
        batch_size: Firestore 배치 크기
        force: True면 기존 값도 덮어씀

    Returns:
        처리 통계
    """
    db = get_db()
    subway = SeoulSubwayCommute()

    if not subway.is_initialized():
        print("[Error] 지하철 모듈 초기화 실패")
        return {"error": "subway module not initialized"}

    stats = {
        "total_processed": 0,
        "updated": 0,
        "skipped_no_address": 0,
        "skipped_no_coords": 0,
        "failed": 0,
    }

    print(f"[Enrich] nearest_station 후처리 시작")
    print(f"[Enrich] 설정: limit={limit}, batch_size={batch_size}, force={force}")

    # nearest_station이 없는 활성 공고 조회
    if force:
        query = db.collection("jobs").where("is_active", "==", True).limit(limit)
    else:
        # nearest_station이 없거나 빈 문자열인 공고
        query = (
            db.collection("jobs")
            .where("is_active", "==", True)
            .where("nearest_station", "==", "")
            .limit(limit)
        )

    docs = list(query.stream())
    print(f"[Enrich] 처리 대상: {len(docs)}건")

    if not docs:
        # nearest_station 필드 자체가 없는 경우도 조회
        query2 = db.collection("jobs").where("is_active", "==", True).limit(limit * 2)
        all_docs = list(query2.stream())
        docs = [d for d in all_docs if "nearest_station" not in d.to_dict()][:limit]
        print(f"[Enrich] nearest_station 필드 없는 공고: {len(docs)}건")

    if not docs:
        print("[Enrich] 처리할 공고 없음")
        return stats

    batch = db.batch()
    batch_count = 0
    now = datetime.now(timezone.utc).isoformat()

    for i, doc in enumerate(docs):
        job = doc.to_dict()
        job_id = doc.id

        try:
            # 주소 확인
            address = job.get("company_address") or job.get("location_full", "")
            if not address:
                stats["skipped_no_address"] += 1
                continue

            # 좌표 파싱
            coords = subway._parse_location(address)
            if not coords:
                stats["skipped_no_coords"] += 1
                continue

            lat, lng = coords

            # 가장 가까운 역 찾기
            station_id, walk_minutes = subway._find_nearest_station(lat, lng)

            if station_id:
                station_info = subway.stations.get(station_id, {})
                nearest_station = station_info.get("name", "")

                # 업데이트
                batch.update(doc.reference, {
                    "nearest_station": nearest_station,
                    "station_walk_minutes": walk_minutes,
                    "updated_at": now,
                })
                stats["updated"] += 1
                batch_count += 1

            stats["total_processed"] += 1

            # 배치 커밋
            if batch_count >= batch_size:
                await asyncio.to_thread(batch.commit)
                print(f"[Enrich] 배치 저장: {batch_count}건 (진행: {i+1}/{len(docs)})")
                batch = db.batch()
                batch_count = 0

        except Exception as e:
            stats["failed"] += 1
            if settings.DEBUG:
                print(f"[Enrich] 실패 ({job_id}): {e}")

    # 남은 배치 커밋
    if batch_count > 0:
        await asyncio.to_thread(batch.commit)
        print(f"[Enrich] 최종 배치 저장: {batch_count}건")

    print(f"\n[Enrich] 완료")
    print(f"  - 처리: {stats['total_processed']}건")
    print(f"  - 업데이트: {stats['updated']}건")
    print(f"  - 주소 없음: {stats['skipped_no_address']}건")
    print(f"  - 좌표 파싱 실패: {stats['skipped_no_coords']}건")
    print(f"  - 실패: {stats['failed']}건")

    return stats


async def main():
    parser = argparse.ArgumentParser(description="nearest_station 후처리 배치")
    parser.add_argument("--limit", type=int, default=1000, help="최대 처리 건수")
    parser.add_argument("--batch-size", type=int, default=100, help="Firestore 배치 크기")
    parser.add_argument("--force", action="store_true", help="기존 값도 덮어씀")

    args = parser.parse_args()

    await enrich_nearest_station(
        limit=args.limit,
        batch_size=args.batch_size,
        force=args.force
    )


if __name__ == "__main__":
    asyncio.run(main())
