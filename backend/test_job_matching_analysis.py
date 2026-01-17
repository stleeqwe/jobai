#!/usr/bin/env python3
"""
직무 매칭 정확도 심층 분석 테스트

문제: 검색 결과에 관련 없는 공고가 포함되는 현상
목표: 원인 파악 및 개선 방향 도출
"""

import asyncio
import httpx
import json
from typing import Optional, Dict, List
from collections import Counter, defaultdict
from datetime import datetime

API_BASE = "http://localhost:8000"

LOCATIONS = {
    "강남역": {"latitude": 37.497916, "longitude": 127.027632, "address": "강남역"},
}

# 분석 대상 직무
ANALYSIS_JOBS = [
    {
        "name": "프론트엔드 개발자",
        "exact_keywords": ["프론트엔드", "frontend", "프론트", "front-end"],
        "related_keywords": ["react", "vue", "angular", "javascript", "웹개발", "웹퍼블리셔"],
        "unrelated_keywords": ["백엔드", "backend", "서버", "java", "python", "마케팅", "디자인", "영업"]
    },
    {
        "name": "백엔드 개발자",
        "exact_keywords": ["백엔드", "backend", "서버개발", "server"],
        "related_keywords": ["java", "python", "node", "spring", "django", "api"],
        "unrelated_keywords": ["프론트엔드", "frontend", "react", "vue", "마케팅", "디자인"]
    },
    {
        "name": "UI/UX 디자이너",
        "exact_keywords": ["ui", "ux", "ui/ux", "uiux"],
        "related_keywords": ["사용자경험", "인터페이스", "프로덕트디자인", "figma"],
        "unrelated_keywords": ["그래픽", "영상", "3d", "마케팅", "개발", "백엔드"]
    },
    {
        "name": "데이터 분석가",
        "exact_keywords": ["데이터분석", "data analyst", "분석가"],
        "related_keywords": ["bi", "sql", "tableau", "통계", "애널리스트"],
        "unrelated_keywords": ["데이터엔지니어", "머신러닝", "개발", "마케팅"]
    },
    {
        "name": "퍼포먼스 마케터",
        "exact_keywords": ["퍼포먼스", "performance", "퍼포먼스마케터"],
        "related_keywords": ["광고", "cpc", "cpa", "페이스북", "구글애즈"],
        "unrelated_keywords": ["콘텐츠", "브랜드", "pr", "개발", "디자인"]
    },
]


class JobMatchingAnalyzer:
    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None

    async def setup(self):
        self.client = httpx.AsyncClient(timeout=60.0)

    async def teardown(self):
        if self.client:
            await self.client.aclose()

    async def chat(self, message: str) -> Dict:
        payload = {
            "message": message,
            "user_location": LOCATIONS["강남역"]
        }
        response = await self.client.post(f"{API_BASE}/chat", json=payload)
        return response.json()

    def analyze_title_match(self, title: str, job_config: Dict) -> Dict:
        """타이틀 매칭 분석"""
        title_lower = title.lower()

        exact_match = any(kw.lower() in title_lower for kw in job_config["exact_keywords"])
        related_match = any(kw.lower() in title_lower for kw in job_config["related_keywords"])
        unrelated_match = any(kw.lower() in title_lower for kw in job_config["unrelated_keywords"])

        if exact_match:
            category = "정확매칭"
        elif related_match:
            category = "유사매칭"
        elif unrelated_match:
            category = "무관공고"
        else:
            category = "분류불가"

        return {
            "category": category,
            "exact": exact_match,
            "related": related_match,
            "unrelated": unrelated_match,
        }

    async def analyze_job(self, job_config: Dict) -> Dict:
        """단일 직무 분석"""
        job_name = job_config["name"]
        query = f"강남에서 연봉 무관 {job_name}"

        print(f"\n{'='*70}")
        print(f"분석 대상: {job_name}")
        print(f"검색 쿼리: {query}")
        print("="*70)

        resp = await self.chat(query)
        jobs = resp.get("jobs", [])
        params = resp.get("search_params", {})
        search_keywords = params.get("job_keywords", [])

        print(f"\n[검색 파라미터]")
        print(f"  - AI가 생성한 job_keywords: {search_keywords}")

        if not jobs:
            print(f"\n결과 없음")
            return {"job_name": job_name, "total": 0, "categories": {}}

        # 결과 분석
        categories = defaultdict(list)
        title_words = Counter()

        print(f"\n[결과 분석] 총 {len(jobs)}건")
        print("-"*70)

        for i, job in enumerate(jobs[:20]):  # 상위 20개 분석
            title = job.get("title", "")
            company = job.get("company_name", "")
            job_keywords = job.get("job_keywords", [])

            analysis = self.analyze_title_match(title, job_config)
            categories[analysis["category"]].append({
                "title": title,
                "company": company,
            })

            # 타이틀 단어 수집
            for word in title.split():
                if len(word) > 1:
                    title_words[word] += 1

            # 상세 출력
            status = {
                "정확매칭": "✅",
                "유사매칭": "🔶",
                "무관공고": "❌",
                "분류불가": "❓"
            }[analysis["category"]]

            print(f"  {status} [{analysis['category']}] {title[:50]}")

        # 요약
        print(f"\n[분류 요약]")
        total = len(jobs[:20])
        for cat in ["정확매칭", "유사매칭", "무관공고", "분류불가"]:
            count = len(categories[cat])
            rate = count / total * 100 if total > 0 else 0
            print(f"  - {cat}: {count}건 ({rate:.0f}%)")

        # 타이틀에 자주 등장하는 단어
        print(f"\n[타이틀 빈출 단어 Top 10]")
        for word, count in title_words.most_common(10):
            print(f"  - {word}: {count}회")

        # 문제 공고 상세 분석
        if categories["무관공고"] or categories["분류불가"]:
            print(f"\n[문제 공고 상세 분석]")
            problem_jobs = categories["무관공고"] + categories["분류불가"]
            for pj in problem_jobs[:5]:
                print(f"  ❌ {pj['company']} - {pj['title']}")

        return {
            "job_name": job_name,
            "search_keywords": search_keywords,
            "total": len(jobs),
            "analyzed": min(len(jobs), 20),
            "categories": {k: len(v) for k, v in categories.items()},
            "accuracy": len(categories["정확매칭"]) / min(len(jobs), 20) * 100 if jobs else 0,
            "relevance": (len(categories["정확매칭"]) + len(categories["유사매칭"])) / min(len(jobs), 20) * 100 if jobs else 0,
        }

    async def analyze_keyword_generation(self):
        """AI 키워드 생성 패턴 분석"""
        print("\n" + "="*70)
        print("AI 키워드 생성 패턴 분석")
        print("="*70)

        test_queries = [
            "프론트엔드 개발자",
            "프론트엔드",
            "FE 개발자",
            "React 개발자",
            "웹 프론트엔드",
            "백엔드 개발자",
            "서버 개발자",
            "Java 개발자",
            "UI/UX 디자이너",
            "UX 디자이너",
            "프로덕트 디자이너",
        ]

        print("\n[쿼리별 생성 키워드]")
        for query in test_queries:
            full_query = f"강남에서 연봉 무관 {query}"
            resp = await self.chat(full_query)
            params = resp.get("search_params", {})
            keywords = params.get("job_keywords", [])

            print(f"\n  '{query}'")
            print(f"    → {keywords}")

    async def analyze_db_matching_logic(self):
        """DB 매칭 로직 분석 - 동일 키워드로 다른 결과가 나오는지"""
        print("\n" + "="*70)
        print("DB 매칭 로직 분석")
        print("="*70)

        # 같은 의미, 다른 표현
        equivalent_queries = [
            ("프론트엔드 개발자", "프론트엔드"),
            ("프론트엔드 개발자", "Frontend Developer"),
            ("백엔드 개발자", "서버 개발자"),
            ("UI/UX 디자이너", "UX 디자이너"),
        ]

        for query1, query2 in equivalent_queries:
            resp1 = await self.chat(f"강남에서 연봉 무관 {query1}")
            resp2 = await self.chat(f"강남에서 연봉 무관 {query2}")

            jobs1 = set(j.get("id") for j in resp1.get("jobs", []))
            jobs2 = set(j.get("id") for j in resp2.get("jobs", []))

            overlap = len(jobs1 & jobs2)
            total = len(jobs1 | jobs2)
            overlap_rate = overlap / total * 100 if total > 0 else 0

            print(f"\n  '{query1}' vs '{query2}'")
            print(f"    - 결과1: {len(jobs1)}건, 결과2: {len(jobs2)}건")
            print(f"    - 중복: {overlap}건, 중복률: {overlap_rate:.0f}%")

    async def analyze_job_keywords_field(self):
        """DB의 job_keywords 필드 분석"""
        print("\n" + "="*70)
        print("DB job_keywords 필드 분석")
        print("="*70)

        resp = await self.chat("강남에서 연봉 무관 프론트엔드 개발자")
        jobs = resp.get("jobs", [])

        print(f"\n[샘플 공고의 job_keywords 필드]")
        for job in jobs[:10]:
            title = job.get("title", "")
            job_keywords = job.get("job_keywords", [])
            print(f"\n  제목: {title}")
            print(f"  keywords: {job_keywords[:10]}...")  # 처음 10개만

    async def run_full_analysis(self):
        """전체 분석 실행"""
        await self.setup()

        print("\n" + "#"*70)
        print("# 직무 매칭 정확도 심층 분석")
        print("#"*70)
        print(f"분석 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # 1. 각 직무별 상세 분석
        all_results = []
        for job_config in ANALYSIS_JOBS:
            result = await self.analyze_job(job_config)
            all_results.append(result)
            await asyncio.sleep(0.5)

        # 2. AI 키워드 생성 패턴 분석
        await self.analyze_keyword_generation()

        # 3. 동의어 쿼리 결과 비교
        await self.analyze_db_matching_logic()

        # 4. job_keywords 필드 분석
        await self.analyze_job_keywords_field()

        # 최종 요약
        print("\n" + "="*70)
        print("최종 분석 요약")
        print("="*70)

        print("\n[직무별 정확도]")
        print("-"*50)
        print(f"{'직무':<20} {'정확매칭':<10} {'관련성':<10} {'총건수':<10}")
        print("-"*50)

        for r in all_results:
            print(f"{r['job_name']:<20} {r['accuracy']:.0f}%{'':<6} {r['relevance']:.0f}%{'':<6} {r['total']}건")

        avg_accuracy = sum(r['accuracy'] for r in all_results) / len(all_results)
        avg_relevance = sum(r['relevance'] for r in all_results) / len(all_results)

        print("-"*50)
        print(f"{'평균':<20} {avg_accuracy:.0f}%{'':<6} {avg_relevance:.0f}%")

        # 문제 원인 분석
        print("\n" + "="*70)
        print("문제 원인 분석")
        print("="*70)

        print("""
[가설 1] AI가 너무 포괄적인 키워드를 생성
  - "프론트엔드 개발자" → ["프론트엔드", "개발자", "React", "Vue", ...]
  - "개발자" 키워드가 백엔드, 풀스택 등 모든 개발 공고를 매칭

[가설 2] DB의 job_keywords 필드가 너무 광범위
  - 하나의 공고에 많은 키워드가 포함되어 있어 과매칭 발생
  - 예: 프론트엔드 공고에 "개발자", "IT", "소프트웨어" 등 일반 키워드 포함

[가설 3] 매칭 로직이 OR 조건으로 동작
  - job_keywords 중 하나라도 매칭되면 결과에 포함
  - AND 조건이나 가중치 적용 필요

[가설 4] 타이틀 우선 정렬이 제대로 동작하지 않음
  - 타이틀에 정확히 매칭되는 공고가 상위에 오지 않음
""")

        await self.teardown()

        return all_results


async def main():
    analyzer = JobMatchingAnalyzer()
    results = await analyzer.run_full_analysis()

    # 결과 저장
    with open("job_matching_analysis.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n결과가 job_matching_analysis.json에 저장되었습니다.")


if __name__ == "__main__":
    asyncio.run(main())
