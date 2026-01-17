#!/usr/bin/env python3
"""
직무 키워드 매칭 및 스코어링 테스트

테스트 목표:
1. title 매칭 (3점) > job_type 매칭 (2점) > job_keywords 매칭 (1점) 순서 확인
2. skills만 포함된 공고도 검색되는지 확인
3. 다양한 키워드 조합 테스트
"""

import asyncio
import httpx
from typing import Dict, List
from collections import defaultdict

API_BASE = "http://localhost:8000"

# 테스트 케이스: 다양한 키워드 유형
TEST_CASES = [
    # 1. Title에 직접 포함될 키워드
    {
        "name": "Title 매칭 테스트",
        "query": "프론트엔드 개발자",
        "expected_title_keywords": ["프론트엔드", "프론트", "frontend", "front-end"],
        "description": "제목에 '프론트엔드' 포함된 공고가 상위에 나와야 함"
    },

    # 2. Work Fields (직무분류) 키워드
    {
        "name": "Work Fields 매칭 테스트",
        "query": "웹개발",
        "expected_title_keywords": ["웹개발", "웹 개발", "web"],
        "description": "직무분류에 '웹개발' 포함된 공고 검색"
    },

    # 3. Skills (기술스택) 키워드
    {
        "name": "Skills 매칭 테스트 - React",
        "query": "React 개발자",
        "expected_title_keywords": ["react"],
        "description": "skills에 React 포함된 공고도 검색되어야 함"
    },
    {
        "name": "Skills 매칭 테스트 - Python",
        "query": "Python 개발자",
        "expected_title_keywords": ["python"],
        "description": "skills에 Python 포함된 공고도 검색되어야 함"
    },
    {
        "name": "Skills 매칭 테스트 - AWS",
        "query": "AWS 엔지니어",
        "expected_title_keywords": ["aws", "클라우드", "cloud"],
        "description": "skills에 AWS 포함된 공고도 검색되어야 함"
    },

    # 4. 복합 키워드 (title + skills)
    {
        "name": "복합 매칭 테스트 - 백엔드 + Java",
        "query": "Java 백엔드 개발자",
        "expected_title_keywords": ["백엔드", "backend", "java", "서버"],
        "description": "제목에 백엔드 + skills에 Java 둘 다 매칭"
    },

    # 5. 영문 키워드
    {
        "name": "영문 키워드 테스트",
        "query": "Frontend Developer",
        "expected_title_keywords": ["frontend", "프론트엔드", "front-end"],
        "description": "영문 키워드로도 검색 가능해야 함"
    },

    # 6. 특수 직무
    {
        "name": "UI/UX 디자이너 테스트",
        "query": "UI/UX 디자이너",
        "expected_title_keywords": ["ui", "ux", "ui/ux", "디자이너"],
        "description": "UI/UX 관련 공고 검색"
    },

    # 7. 데이터 관련 직무
    {
        "name": "데이터 엔지니어 테스트",
        "query": "데이터 엔지니어",
        "expected_title_keywords": ["데이터", "data", "엔지니어"],
        "description": "데이터 엔지니어 공고 검색"
    },
]


async def search_jobs(client: httpx.AsyncClient, query: str) -> Dict:
    """검색 수행"""
    payload = {
        "message": f"강남에서 {query} 채용공고 찾아줘 연봉은 상관없어",
        "user_location": {"latitude": 37.497916, "longitude": 127.027632, "address": "강남역"}
    }
    response = await client.post(f"{API_BASE}/chat", json=payload)
    return response.json()


def analyze_job_match(job: Dict, keywords: List[str]) -> Dict:
    """공고가 어떤 필드에서 매칭되었는지 분석"""
    title = job.get("title", "").lower()
    job_kws = [kw.lower() for kw in job.get("job_keywords", [])]

    result = {
        "title_match": False,
        "keywords_match": False,
        "matched_in": []
    }

    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in title:
            result["title_match"] = True
            result["matched_in"].append(f"title:{kw}")
        if any(kw_lower in jk for jk in job_kws):
            result["keywords_match"] = True
            result["matched_in"].append(f"keywords:{kw}")

    return result


async def run_test_case(client: httpx.AsyncClient, test_case: Dict) -> Dict:
    """단일 테스트 케이스 실행"""
    print(f"\n{'='*70}")
    print(f"테스트: {test_case['name']}")
    print(f"쿼리: {test_case['query']}")
    print(f"설명: {test_case['description']}")
    print("="*70)

    result = await search_jobs(client, test_case['query'])
    jobs = result.get("jobs", [])
    search_params = result.get("search_params", {})
    ai_keywords = search_params.get("job_keywords", [])

    print(f"\n[AI 생성 키워드]: {ai_keywords}")
    print(f"[검색 결과]: {len(jobs)}건")

    if not jobs:
        return {
            "name": test_case["name"],
            "total": 0,
            "title_match_count": 0,
            "keywords_only_count": 0,
            "no_match_count": 0,
            "success": False
        }

    # 상위 20건 분석
    title_match_count = 0
    keywords_only_count = 0
    no_match_count = 0

    print(f"\n[상위 20건 분석]")
    print("-"*70)

    for i, job in enumerate(jobs[:20]):
        title = job.get("title", "")
        job_kws = job.get("job_keywords", [])[:5]  # 처음 5개만

        analysis = analyze_job_match(job, test_case["expected_title_keywords"])

        if analysis["title_match"]:
            status = "✅ Title"
            title_match_count += 1
        elif analysis["keywords_match"]:
            status = "🔶 Keywords"
            keywords_only_count += 1
        else:
            status = "❓ Unknown"
            no_match_count += 1

        print(f"{i+1:2}. [{status}] {title[:45]}")
        if i < 5:  # 상위 5개는 job_keywords도 출력
            print(f"    job_keywords: {job_kws}")

    # 스코어 순서 검증: title 매칭이 상위에 있는지
    first_title_match_idx = -1
    first_keywords_only_idx = -1

    for i, job in enumerate(jobs[:20]):
        analysis = analyze_job_match(job, test_case["expected_title_keywords"])
        if analysis["title_match"] and first_title_match_idx == -1:
            first_title_match_idx = i
        if not analysis["title_match"] and analysis["keywords_match"] and first_keywords_only_idx == -1:
            first_keywords_only_idx = i

    score_order_correct = (
        first_title_match_idx == -1 or
        first_keywords_only_idx == -1 or
        first_title_match_idx < first_keywords_only_idx
    )

    print(f"\n[분석 결과]")
    print(f"  - Title 매칭: {title_match_count}건")
    print(f"  - Keywords만 매칭: {keywords_only_count}건")
    print(f"  - 매칭 불명: {no_match_count}건")
    print(f"  - 스코어 순서 정상: {'✅' if score_order_correct else '❌'}")

    return {
        "name": test_case["name"],
        "total": len(jobs),
        "analyzed": 20,
        "title_match_count": title_match_count,
        "keywords_only_count": keywords_only_count,
        "no_match_count": no_match_count,
        "score_order_correct": score_order_correct,
        "ai_keywords": ai_keywords,
        "success": title_match_count + keywords_only_count > 0
    }


async def test_skills_only_match(client: httpx.AsyncClient):
    """Skills만 포함된 공고 검색 테스트"""
    print(f"\n{'#'*70}")
    print("# Skills-Only 매칭 심층 테스트")
    print("#"*70)

    # 특정 기술스택으로 검색
    skills_tests = [
        ("TypeScript", ["typescript", "ts"]),
        ("Docker", ["docker", "컨테이너"]),
        ("Kubernetes", ["kubernetes", "k8s", "쿠버네티스"]),
        ("Next.js", ["next.js", "nextjs", "next"]),
    ]

    for skill_query, expected_kws in skills_tests:
        print(f"\n[{skill_query} 검색]")
        result = await search_jobs(client, f"{skill_query} 개발자")
        jobs = result.get("jobs", [])

        if not jobs:
            print(f"  결과 없음")
            continue

        # 제목에 skill이 없고 job_keywords에만 있는 공고 찾기
        skills_only_jobs = []
        for job in jobs[:30]:
            title = job.get("title", "").lower()
            job_kws = [kw.lower() for kw in job.get("job_keywords", [])]

            title_has_skill = any(kw in title for kw in expected_kws)
            keywords_has_skill = any(
                any(kw in jk for kw in expected_kws)
                for jk in job_kws
            )

            if not title_has_skill and keywords_has_skill:
                skills_only_jobs.append(job)

        print(f"  총 {len(jobs)}건 중 skills-only 매칭: {len(skills_only_jobs)}건")

        for job in skills_only_jobs[:3]:
            print(f"    - {job.get('title', '')[:40]}")
            print(f"      keywords: {job.get('job_keywords', [])[:8]}")


async def main():
    print("#"*70)
    print("# 직무 키워드 매칭 & 스코어링 종합 테스트")
    print("#"*70)

    async with httpx.AsyncClient(timeout=60.0) as client:
        all_results = []

        # 1. 기본 테스트 케이스 실행
        for test_case in TEST_CASES:
            result = await run_test_case(client, test_case)
            all_results.append(result)
            await asyncio.sleep(0.5)

        # 2. Skills-only 매칭 테스트
        await test_skills_only_match(client)

        # 3. 최종 요약
        print(f"\n{'='*70}")
        print("최종 요약")
        print("="*70)

        print(f"\n{'테스트명':<30} {'총건수':<8} {'Title':<8} {'KW Only':<8} {'순서':<6}")
        print("-"*70)

        for r in all_results:
            order_status = "✅" if r.get("score_order_correct", False) else "❌"
            print(f"{r['name']:<30} {r['total']:<8} {r['title_match_count']:<8} {r['keywords_only_count']:<8} {order_status:<6}")

        # 성공률 계산
        success_count = sum(1 for r in all_results if r["success"])
        total_count = len(all_results)

        print("-"*70)
        print(f"테스트 성공률: {success_count}/{total_count} ({success_count/total_count*100:.0f}%)")

        # 스코어 순서 정확도
        order_correct_count = sum(1 for r in all_results if r.get("score_order_correct", False))
        print(f"스코어 순서 정확률: {order_correct_count}/{total_count} ({order_correct_count/total_count*100:.0f}%)")


if __name__ == "__main__":
    asyncio.run(main())
