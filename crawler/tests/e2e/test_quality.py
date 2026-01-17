#!/usr/bin/env python3
"""E2E 테스트 4: 데이터 품질 검증"""

import asyncio
import sys
import os
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings
from app.db.firestore import get_db


async def test_data_quality():
    """데이터 품질 검증"""
    print("=" * 70)
    print("E2E 테스트 4: 데이터 품질 검증")
    print("=" * 70)

    if not settings.GOOGLE_CLOUD_PROJECT and not settings.GOOGLE_APPLICATION_CREDENTIALS:
        print("[Error] GOOGLE_CLOUD_PROJECT 또는 GOOGLE_APPLICATION_CREDENTIALS 설정 필요")
        return

    db = get_db()
    jobs_ref = db.collection("jobs")

    # 샘플 1000건 조회
    print("\n[1] 샘플 1000건 분석")
    print("-" * 50)

    sample_jobs = []
    for doc in jobs_ref.limit(1000).stream():
        sample_jobs.append(doc.to_dict())

    print(f"  샘플 수: {len(sample_jobs)}건")

    # 필수 필드 검증
    print("\n[2] 필수 필드 완성도")
    print("-" * 50)

    required_fields = ["id", "title", "company_name", "location_full", "url"]
    optional_fields = ["salary_text", "salary_min", "job_keywords", "experience_type"]

    for field in required_fields + optional_fields:
        non_null = sum(1 for j in sample_jobs if j.get(field))
        pct = non_null / len(sample_jobs) * 100
        required = "필수" if field in required_fields else "선택"
        status = "✅" if pct >= 80 else "⚠️" if pct >= 50 else "❌"
        print(f"  {status} {field} ({required}): {non_null}/{len(sample_jobs)} ({pct:.1f}%)")

    # 연봉 데이터 분석
    print("\n[3] 연봉 데이터 분석")
    print("-" * 50)

    salary_jobs = [j for j in sample_jobs if j.get("salary_min")]
    print(f"  연봉 정보 있음: {len(salary_jobs)}건 ({len(salary_jobs)/len(sample_jobs)*100:.1f}%)")

    if salary_jobs:
        salaries = [j["salary_min"] for j in salary_jobs]
        print(f"  최소: {min(salaries):,}만원")
        print(f"  최대: {max(salaries):,}만원")
        print(f"  평균: {sum(salaries)/len(salaries):,.0f}만원")

    # 연봉 텍스트 분석
    salary_texts = [j.get("salary_text", "") for j in sample_jobs]
    text_categories = Counter()
    for st in salary_texts:
        if not st:
            text_categories["없음"] += 1
        elif "내규" in st or "협의" in st:
            text_categories["협의/내규"] += 1
        elif "연봉" in st:
            text_categories["연봉 명시"] += 1
        else:
            text_categories["기타"] += 1

    print(f"\n  연봉 텍스트 분포:")
    for cat, cnt in text_categories.most_common():
        print(f"    {cat}: {cnt}건 ({cnt/len(sample_jobs)*100:.1f}%)")

    # 위치 데이터 분석
    print("\n[4] 위치 데이터 분석")
    print("-" * 50)

    location_jobs = [j for j in sample_jobs if j.get("location_full")]
    seoul_jobs = [j for j in location_jobs if "서울" in j.get("location_full", "")]
    print(f"  위치 정보 있음: {len(location_jobs)}건")
    print(f"  서울 공고: {len(seoul_jobs)}건 ({len(seoul_jobs)/len(sample_jobs)*100:.1f}%)")

    # 구별 분포
    gu_counter = Counter()
    for job in seoul_jobs:
        loc = job.get("location_full", "")
        for part in loc.split():
            if "구" in part and "서울" not in part:
                gu_counter[part] += 1
                break

    print(f"\n  서울 구별 분포 (상위 10):")
    for gu, cnt in gu_counter.most_common(10):
        print(f"    {gu}: {cnt}건")

    # 직무 키워드 분석
    print("\n[5] 직무 키워드 분석")
    print("-" * 50)

    keyword_jobs = [j for j in sample_jobs if j.get("job_keywords")]
    print(f"  키워드 있음: {len(keyword_jobs)}건 ({len(keyword_jobs)/len(sample_jobs)*100:.1f}%)")

    all_keywords = []
    for job in keyword_jobs:
        all_keywords.extend(job.get("job_keywords", []))

    if all_keywords:
        kw_counter = Counter(all_keywords)
        print(f"\n  주요 키워드 (상위 15):")
        for kw, cnt in kw_counter.most_common(15):
            print(f"    {kw}: {cnt}건")

    # URL 유효성 검사
    print("\n[6] URL 유효성 검사")
    print("-" * 50)

    url_jobs = [j for j in sample_jobs if j.get("url")]
    valid_urls = [j for j in url_jobs if j.get("url", "").startswith("http")]
    jobkorea_urls = [j for j in valid_urls if "jobkorea" in j.get("url", "")]

    print(f"  URL 있음: {len(url_jobs)}건")
    print(f"  유효 URL: {len(valid_urls)}건")
    print(f"  잡코리아 URL: {len(jobkorea_urls)}건")

    # 품질 점수 계산
    print("\n" + "=" * 70)
    print("품질 점수 요약")
    print("=" * 70)

    scores = {
        "필수 필드": sum(1 for f in required_fields if sum(1 for j in sample_jobs if j.get(f)) / len(sample_jobs) >= 0.9) / len(required_fields) * 100,
        "연봉 정보": len([j for j in sample_jobs if j.get("salary_text")]) / len(sample_jobs) * 100,
        "위치 정보": len(location_jobs) / len(sample_jobs) * 100,
        "서울 비율": len(seoul_jobs) / len(sample_jobs) * 100,
        "키워드": len(keyword_jobs) / len(sample_jobs) * 100,
    }

    total_score = sum(scores.values()) / len(scores)

    for name, score in scores.items():
        status = "✅" if score >= 80 else "⚠️" if score >= 50 else "❌"
        print(f"  {status} {name}: {score:.1f}%")

    print(f"\n  종합 점수: {total_score:.1f}%")

    if total_score >= 80:
        print("  → 데이터 품질 양호")
    elif total_score >= 60:
        print("  → 데이터 품질 보통 (일부 개선 필요)")
    else:
        print("  → 데이터 품질 미흡 (개선 필요)")

    print("\n" + "=" * 70)
    print("품질 검증 완료")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_data_quality())
