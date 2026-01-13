"""채용공고 데이터 분석 스크립트"""

import asyncio
import os
import sys
from collections import Counter

# 프로젝트 경로 설정
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'crawler'))

from google.cloud import firestore


async def analyze_job_data():
    """Firestore 채용공고 데이터 분석"""

    # 환경변수 설정
    os.environ.setdefault('GOOGLE_CLOUD_PROJECT', 'jobchat-1768149763')
    credentials_path = os.path.expanduser('~/jobchat-credentials.json')
    if os.path.exists(credentials_path):
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path

    db = firestore.AsyncClient()

    print("=" * 60)
    print("JobChat 채용공고 데이터 분석")
    print("=" * 60)

    # 전체 공고 수
    total_query = db.collection("jobs").where("is_active", "==", True)

    job_categories = Counter()
    job_types = Counter()
    mvp_categories = Counter()
    locations = Counter()
    empty_fields = {
        "job_type": 0,
        "job_category": 0,
        "mvp_category": 0,
        "job_keywords": 0,
    }
    total_count = 0

    print("\n데이터 수집 중...")

    async for doc in total_query.stream():
        job = doc.to_dict()
        total_count += 1

        # 카테고리 분석
        category = job.get("job_category", "")
        job_categories[category if category else "(빈값)"] += 1

        # 직무 타입 분석
        jtype = job.get("job_type", "")
        job_types[jtype if jtype else "(빈값)"] += 1

        # MVP 카테고리 분석
        mvp_cat = job.get("mvp_category", "")
        mvp_categories[mvp_cat if mvp_cat else "(없음)"] += 1

        # 위치 분석
        sido = job.get("location_sido", "")
        locations[sido if sido else "(빈값)"] += 1

        # 빈 필드 체크
        if not job.get("job_type"):
            empty_fields["job_type"] += 1
        if not job.get("job_category"):
            empty_fields["job_category"] += 1
        if not job.get("mvp_category"):
            empty_fields["mvp_category"] += 1
        if not job.get("job_keywords"):
            empty_fields["job_keywords"] += 1

    # 결과 출력
    print(f"\n총 활성 공고 수: {total_count}건")

    print("\n" + "=" * 60)
    print("1. job_category 분포")
    print("=" * 60)
    for cat, count in job_categories.most_common():
        pct = count / total_count * 100 if total_count > 0 else 0
        bar = "█" * int(pct / 2)
        print(f"  {cat:20s}: {count:4d}건 ({pct:5.1f}%) {bar}")

    print("\n" + "=" * 60)
    print("2. job_type 분포 (상위 20개)")
    print("=" * 60)
    for jtype, count in job_types.most_common(20):
        pct = count / total_count * 100 if total_count > 0 else 0
        print(f"  {jtype:25s}: {count:4d}건 ({pct:5.1f}%)")

    print("\n" + "=" * 60)
    print("3. mvp_category 분포")
    print("=" * 60)
    for mvp, count in mvp_categories.most_common():
        pct = count / total_count * 100 if total_count > 0 else 0
        bar = "█" * int(pct / 2)
        print(f"  {mvp:20s}: {count:4d}건 ({pct:5.1f}%) {bar}")

    print("\n" + "=" * 60)
    print("4. location_sido 분포")
    print("=" * 60)
    for loc, count in locations.most_common():
        pct = count / total_count * 100 if total_count > 0 else 0
        print(f"  {loc:15s}: {count:4d}건 ({pct:5.1f}%)")

    print("\n" + "=" * 60)
    print("5. 빈 필드 분석 (문제점)")
    print("=" * 60)
    for field, count in empty_fields.items():
        pct = count / total_count * 100 if total_count > 0 else 0
        status = "⚠️ 문제" if pct > 5 else "✓ 양호"
        print(f"  {field:20s}: {count:4d}건 비어있음 ({pct:5.1f}%) {status}")

    # 기타 카테고리 상세 분석
    if job_categories.get("기타", 0) > 0:
        print("\n" + "=" * 60)
        print("6. '기타' 카테고리 상세 분석")
        print("=" * 60)

        etc_job_types = Counter()
        etc_query = db.collection("jobs").where("job_category", "==", "기타")

        async for doc in etc_query.stream():
            job = doc.to_dict()
            jtype_raw = job.get("job_type_raw", "") or job.get("job_type", "")
            title = job.get("title", "")[:30]
            etc_job_types[f"{jtype_raw or title}"] += 1

        print("  '기타' 카테고리의 job_type_raw (상위 15개):")
        for jtype, count in etc_job_types.most_common(15):
            print(f"    - {jtype}: {count}건")

    print("\n" + "=" * 60)
    print("분석 완료")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(analyze_job_data())
