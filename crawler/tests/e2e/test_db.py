#!/usr/bin/env python3
"""E2E 테스트 1: Firestore DB 데이터 확인"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.firestore import get_job_stats, get_db


async def test_db_data():
    """DB 데이터 상태 확인"""
    print("=" * 70)
    print("E2E 테스트 1: Firestore DB 데이터 확인")
    print("=" * 70)

    # 1. 기본 통계
    print("\n[1] 기본 통계")
    print("-" * 50)
    stats = await get_job_stats()
    print(f"  총 공고: {stats['total_jobs']:,}건")
    print(f"  활성 공고: {stats['active_jobs']:,}건")
    print(f"  마지막 크롤링: {stats.get('last_crawl', 'N/A')}")

    # 2. 샘플 데이터 확인
    print("\n[2] 샘플 데이터 (최근 5건)")
    print("-" * 50)
    db = get_db()
    jobs_ref = db.collection("jobs")

    # 최근 업데이트된 5건
    recent_jobs = jobs_ref.order_by("updated_at", direction="DESCENDING").limit(5).stream()

    for i, job in enumerate(recent_jobs, 1):
        data = job.to_dict()
        print(f"\n  [{i}] {data.get('id', 'N/A')}")
        print(f"      제목: {data.get('title', 'N/A')[:50]}...")
        print(f"      회사: {data.get('company_name', 'N/A')}")
        print(f"      위치: {data.get('location_full', 'N/A')}")
        print(f"      연봉: {data.get('salary_text', 'N/A')}")
        print(f"      최근역: {data.get('nearest_station', 'N/A')}")
        print(f"      활성: {data.get('is_active', 'N/A')}")

    # 3. 필드 완성도 확인
    print("\n[3] 필드 완성도 (100건 샘플)")
    print("-" * 50)

    sample_jobs = jobs_ref.limit(100).stream()

    field_counts = {
        "title": 0,
        "company_name": 0,
        "location_full": 0,
        "salary_text": 0,
        "salary_min": 0,
        "nearest_station": 0,
        "job_keywords": 0,
        "is_active": 0,
    }

    total = 0
    for job in sample_jobs:
        data = job.to_dict()
        total += 1
        for field in field_counts:
            if data.get(field):
                field_counts[field] += 1

    for field, count in field_counts.items():
        pct = (count / total * 100) if total > 0 else 0
        status = "✅" if pct >= 80 else "⚠️" if pct >= 50 else "❌"
        print(f"  {status} {field}: {count}/{total} ({pct:.1f}%)")

    # 4. 지역 분포
    print("\n[4] 지역 분포 (상위 10개)")
    print("-" * 50)

    from collections import Counter
    all_jobs = jobs_ref.limit(1000).stream()
    locations = []
    for job in all_jobs:
        data = job.to_dict()
        loc = data.get("location_gu", data.get("location_full", ""))
        if loc:
            # 구 이름 추출
            if "구" in loc:
                gu = loc.split()[0] if " " in loc else loc
                for part in loc.split():
                    if "구" in part:
                        gu = part
                        break
                locations.append(gu)

    loc_counter = Counter(locations)
    for loc, count in loc_counter.most_common(10):
        print(f"  {loc}: {count}건")

    # 5. 직무 키워드 분포
    print("\n[5] 직무 키워드 분포")
    print("-" * 50)

    all_jobs = jobs_ref.limit(1000).stream()
    keywords = []
    for job in all_jobs:
        data = job.to_dict()
        kws = data.get("job_keywords", [])
        if kws:
            keywords.extend(kws)

    kw_counter = Counter(keywords)
    for kw, count in kw_counter.most_common(15):
        print(f"  {kw}: {count}건")

    print("\n" + "=" * 70)
    print("DB 테스트 완료")
    print("=" * 70)

    return stats


if __name__ == "__main__":
    asyncio.run(test_db_data())
