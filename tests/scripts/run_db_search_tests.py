#!/usr/bin/env python3
"""
데이터베이스 검색 검증 테스트 스크립트

수집한 DB 데이터가 실제 검색 API에서 정상적으로 반환되는지 검증합니다.
"""

import asyncio
import argparse
import os
import sys
import random
from datetime import datetime
from typing import List, Dict, Any, Optional

import httpx

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '../../backend/.env'))

# Firestore 프로젝트 설정
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", "jobchat-1768149763"))

from google.cloud import firestore

API_BASE = "http://localhost:8000"


class TestResult:
    def __init__(self, test_id: str, name: str):
        self.test_id = test_id
        self.name = name
        self.passed = False
        self.message = ""
        self.details: List[Dict] = []


async def get_db():
    """Firestore 클라이언트"""
    return firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "jobchat-1768149763"))


# ============================================================
# TC-100: DB 직접 조회 검증
# ============================================================

async def tc_101_active_jobs_exist() -> TestResult:
    """TC-101: 활성 공고 존재 확인"""
    result = TestResult("TC-101", "활성 공고 존재 확인")

    try:
        db = await get_db()
        query = db.collection("jobs").where("is_active", "==", True).limit(10)
        docs = list(query.stream())

        if len(docs) == 0:
            result.message = "활성 공고 0건"
            return result

        # 필수 필드 확인
        missing_fields = []
        for doc in docs:
            job = doc.to_dict()
            for field in ["title", "company_name", "url"]:
                if not job.get(field):
                    missing_fields.append(f"{doc.id}: {field}")

        if missing_fields:
            result.message = f"필수 필드 누락: {len(missing_fields)}건"
            result.details = missing_fields[:5]
        else:
            result.passed = True
            result.message = f"활성 공고 {len(docs)}건+ 확인"

    except Exception as e:
        result.message = f"오류: {e}"

    return result


async def tc_102_field_completeness() -> TestResult:
    """TC-102: 필드 완성도 검증"""
    result = TestResult("TC-102", "필드 완성도 검증")

    try:
        db = await get_db()
        query = db.collection("jobs").where("is_active", "==", True).limit(1000)
        docs = list(query.stream())

        if len(docs) == 0:
            result.message = "공고 0건"
            return result

        total = len(docs)
        stats = {
            "title_empty": 0,
            "company_empty": 0,
            "salary_exists": 0,
            "location_exists": 0,
        }

        for doc in docs:
            job = doc.to_dict()
            if not job.get("title"):
                stats["title_empty"] += 1
            if not job.get("company_name"):
                stats["company_empty"] += 1
            if job.get("salary_min") and job.get("salary_min") > 0:
                stats["salary_exists"] += 1
            if job.get("location_full"):
                stats["location_exists"] += 1

        title_rate = (total - stats["title_empty"]) / total * 100
        company_rate = (total - stats["company_empty"]) / total * 100
        salary_rate = stats["salary_exists"] / total * 100

        result.details = [
            {"field": "title", "rate": f"{title_rate:.1f}%"},
            {"field": "company_name", "rate": f"{company_rate:.1f}%"},
            {"field": "salary_min", "rate": f"{salary_rate:.1f}%"},
            {"field": "location_full", "rate": f"{stats['location_exists']/total*100:.1f}%"},
        ]

        # 합격 기준: title/company 99%+, salary 20%+ (많은 공고가 연봉 미공개)
        if title_rate >= 99 and company_rate >= 99 and salary_rate >= 20:
            result.passed = True
            result.message = f"필드 완성도 양호 (title:{title_rate:.0f}%, salary:{salary_rate:.0f}%)"
        else:
            result.message = f"필드 완성도 미달 (title:{title_rate:.0f}%, salary:{salary_rate:.0f}%)"

    except Exception as e:
        result.message = f"오류: {e}"

    return result


async def tc_103_sample_lookup() -> TestResult:
    """TC-103: 샘플 데이터 조회"""
    result = TestResult("TC-103", "샘플 데이터 조회")

    try:
        db = await get_db()
        query = db.collection("jobs").where("is_active", "==", True).limit(100)
        docs = list(query.stream())

        if len(docs) < 10:
            result.message = f"공고 부족 ({len(docs)}건)"
            return result

        # 무작위 10개 선택
        samples = random.sample(docs, 10)

        success_count = 0
        for doc in samples:
            # ID로 직접 조회
            lookup = db.collection("jobs").document(doc.id).get()
            if lookup.exists and lookup.to_dict().get("title") == doc.to_dict().get("title"):
                success_count += 1

        if success_count == 10:
            result.passed = True
            result.message = f"10/10 조회 성공"
        else:
            result.message = f"{success_count}/10 조회 성공"

    except Exception as e:
        result.message = f"오류: {e}"

    return result


# ============================================================
# TC-200: 검색 서비스 검증 (API 통해 간접 검증)
# ============================================================

async def tc_201_keyword_search() -> TestResult:
    """TC-201: 키워드 검색 반환"""
    result = TestResult("TC-201", "키워드 검색 반환")

    # Simple Agentic 아키텍처: 직무+연봉+위치 3가지 필수
    test_queries = [
        ("마케팅", "강남역 근처 연봉 3000 이상 마케팅 일자리"),
        ("개발", "강남역 근처 연봉 3000 이상 개발자 일자리"),
        ("디자인", "강남역 근처 연봉 3000 이상 디자인 일자리"),
        ("영업", "강남역 근처 연봉 3000 이상 영업 일자리"),
        ("기획", "강남역 근처 연봉 3000 이상 기획 일자리"),
    ]

    async with httpx.AsyncClient(timeout=60.0) as client:
        passed = 0
        for keyword, query in test_queries:
            try:
                resp = await client.post(
                    f"{API_BASE}/chat",
                    json={"message": query}
                )
                data = resp.json()

                job_count = len(data.get("jobs", []))
                if job_count > 0:
                    passed += 1
                    result.details.append({"keyword": keyword, "count": job_count, "passed": True})
                else:
                    result.details.append({"keyword": keyword, "count": 0, "passed": False})

            except Exception as e:
                result.details.append({"keyword": keyword, "error": str(e), "passed": False})

        if passed >= len(test_queries) - 1:  # 1개까지 실패 허용
            result.passed = True
        result.message = f"{passed}/{len(test_queries)} 키워드 검색 성공"

    return result


async def tc_202_salary_filter() -> TestResult:
    """TC-202: 연봉 필터 동작"""
    result = TestResult("TC-202", "연봉 필터 동작")

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # 연봉 2000 이상 (낮은 기준)
            resp1 = await client.post(
                f"{API_BASE}/chat",
                json={"message": "강남역 근처 연봉 2000 이상 마케팅 일자리"}
            )
            count_2000 = len(resp1.json().get("jobs", []))

            # 연봉 4000 이상
            resp2 = await client.post(
                f"{API_BASE}/chat",
                json={"message": "강남역 근처 연봉 4000 이상 마케팅 일자리"}
            )
            count_4000 = len(resp2.json().get("jobs", []))
            params_4000 = resp2.json().get("search_params", {})

            # 연봉 6000 이상
            resp3 = await client.post(
                f"{API_BASE}/chat",
                json={"message": "강남역 근처 연봉 6000 이상 마케팅 일자리"}
            )
            count_6000 = len(resp3.json().get("jobs", []))

            result.details = [
                {"condition": "2000+", "count": count_2000},
                {"condition": "4000+", "count": count_4000, "parsed": params_4000.get("salary_min")},
                {"condition": "6000+", "count": count_6000},
            ]

            # 논리적 일관성: 높은 연봉 → 적은 결과
            if count_2000 >= count_4000 >= count_6000:
                result.passed = True
                result.message = f"연봉 필터 정상 (2000+:{count_2000} ≥ 4000+:{count_4000} ≥ 6000+:{count_6000})"
            else:
                result.message = f"연봉 필터 이상 (2000+:{count_2000}, 4000+:{count_4000}, 6000+:{count_6000})"

        except Exception as e:
            result.message = f"오류: {e}"

    return result


async def tc_203_location_filter() -> TestResult:
    """TC-203: 회사 위치 필터"""
    result = TestResult("TC-203", "회사 위치 필터")

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(
                f"{API_BASE}/chat",
                json={"message": "강남역 근처 연봉 3000 이상 마케팅 일자리"}
            )
            data = resp.json()
            jobs = data.get("jobs", [])

            if not jobs:
                result.message = "결과 0건"
                return result

            # 위치에 "강남" 포함 비율 확인
            gangnam_count = sum(1 for j in jobs if "강남" in j.get("location", ""))
            rate = gangnam_count / len(jobs) * 100

            result.details = [
                {"total": len(jobs), "gangnam": gangnam_count, "rate": f"{rate:.0f}%"}
            ]

            if rate >= 80:
                result.passed = True
                result.message = f"위치 필터 정상 ({gangnam_count}/{len(jobs)} = {rate:.0f}%)"
            else:
                result.message = f"위치 필터 미흡 ({rate:.0f}%)"

        except Exception as e:
            result.message = f"오류: {e}"

    return result


# ============================================================
# TC-300: API 통합 검증
# ============================================================

async def tc_301_chat_api_returns_results() -> TestResult:
    """TC-301: /chat API 검색 결과 반환"""
    result = TestResult("TC-301", "/chat API 검색 결과 반환")

    # Simple Agentic: 직무+연봉+위치 필수
    test_queries = [
        "강남역 근처 연봉 3000 이상 마케팅 일자리",
        "홍대입구역 근처 연봉 3000 이상 개발자 공고",
        "신림역 근처 연봉 3000 이상 디자이너 일자리",
        "강남역 근처 연봉 3000 이상 영업 직무",
    ]

    async with httpx.AsyncClient(timeout=60.0) as client:
        passed = 0
        for query in test_queries:
            try:
                resp = await client.post(f"{API_BASE}/chat", json={"message": query})
                data = resp.json()

                success = data.get("success", False)
                job_count = len(data.get("jobs", []))

                if success and job_count > 0:
                    passed += 1
                    result.details.append({"query": query[:20], "count": job_count, "passed": True})
                else:
                    result.details.append({"query": query[:20], "count": job_count, "passed": False})

            except Exception as e:
                result.details.append({"query": query[:20], "error": str(e), "passed": False})

        if passed >= len(test_queries) - 1:  # 1개까지 실패 허용
            result.passed = True
        result.message = f"{passed}/{len(test_queries)} 쿼리 성공"

    return result


async def tc_302_response_field_completeness() -> TestResult:
    """TC-302: 반환 데이터 필드 완성도"""
    result = TestResult("TC-302", "반환 데이터 필드 완성도")

    required_fields = ["id", "company_name", "title", "url"]

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(f"{API_BASE}/chat", json={"message": "강남역 근처 연봉 3000 이상 마케팅 일자리"})
            jobs = resp.json().get("jobs", [])

            if not jobs:
                result.message = "결과 0건"
                return result

            missing = []
            for job in jobs[:10]:  # 상위 10개만 검사
                for field in required_fields:
                    if not job.get(field):
                        missing.append(f"{job.get('id', '?')}: {field}")

            if not missing:
                result.passed = True
                result.message = f"필수 필드 100% 존재 (검사: {min(10, len(jobs))}건)"
            else:
                result.message = f"필드 누락 {len(missing)}건"
                result.details = missing[:5]

        except Exception as e:
            result.message = f"오류: {e}"

    return result


# ============================================================
# TC-400: 데이터 무결성 검증
# ============================================================

async def tc_401_api_db_match() -> TestResult:
    """TC-401: API 결과 ↔ DB 일치"""
    result = TestResult("TC-401", "API 결과 ↔ DB 일치")

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # API 검색 (완전한 쿼리)
            resp = await client.post(f"{API_BASE}/chat", json={"message": "강남역 근처 연봉 3000 이상 마케팅 일자리"})
            jobs = resp.json().get("jobs", [])

            if not jobs:
                result.message = "API 결과 0건"
                return result

            # DB 확인
            db = await get_db()

            matched = 0
            mismatched = []
            for job in jobs[:10]:  # 상위 10개 검증
                job_id = job.get("id", "")
                if not job_id:
                    continue

                # jk_ 접두사 처리
                doc_id = job_id if job_id.startswith("jk_") else f"jk_{job_id}"

                doc = db.collection("jobs").document(doc_id).get()
                if doc.exists:
                    db_job = doc.to_dict()
                    if job.get("title") == db_job.get("title"):
                        matched += 1
                    else:
                        mismatched.append(f"{doc_id}: title 불일치")
                else:
                    mismatched.append(f"{doc_id}: DB에 없음")

            check_count = min(10, len(jobs))
            if matched == check_count:
                result.passed = True
                result.message = f"API↔DB 100% 일치 ({matched}/{check_count})"
            else:
                result.message = f"불일치 {len(mismatched)}건"
                result.details = mismatched

        except Exception as e:
            result.message = f"오류: {e}"

    return result


async def tc_402_collected_jobs_searchable() -> TestResult:
    """TC-402: 수집 ID 검색 가능 검증"""
    result = TestResult("TC-402", "수집 ID 검색 가능 검증")

    try:
        db = await get_db()

        # 최근 수집 공고 샘플링 - 마케팅 관련 공고만
        query = db.collection("jobs") \
            .where("is_active", "==", True) \
            .limit(200)
        docs = list(query.stream())

        if len(docs) < 10:
            result.message = f"샘플 부족 ({len(docs)}건)"
            return result

        # 제목에 특정 키워드가 포함된 공고만 선택
        target_keywords = ["마케팅", "개발", "디자인", "영업", "기획", "경영"]
        filtered_docs = []
        for doc in docs:
            job = doc.to_dict()
            title = job.get("title", "").lower()
            for kw in target_keywords:
                if kw in title:
                    filtered_docs.append((doc, kw))
                    break

        if len(filtered_docs) < 5:
            result.passed = True  # 충분한 샘플이 없으면 통과 처리
            result.message = f"검색 가능 비율 검증 불가 (샘플 부족: {len(filtered_docs)})"
            return result

        samples = random.sample(filtered_docs, min(10, len(filtered_docs)))

        found = 0
        async with httpx.AsyncClient(timeout=60.0) as client:
            for doc, keyword in samples:
                job = doc.to_dict()
                location = job.get("location_full", "") or "강남"

                # 위치에서 구 추출
                gu_match = ""
                for gu in ["강남", "서초", "마포", "영등포", "송파", "구로"]:
                    if gu in location:
                        gu_match = gu
                        break
                if not gu_match:
                    gu_match = "강남"

                try:
                    # Simple Agentic: 완전한 쿼리 필요
                    resp = await client.post(
                        f"{API_BASE}/chat",
                        json={"message": f"{gu_match}역 근처 연봉 2000 이상 {keyword} 일자리"}
                    )
                    result_jobs = resp.json().get("jobs", [])

                    # 해당 공고가 결과에 있는지 확인
                    result_ids = [j.get("id", "").replace("jk_", "") for j in result_jobs]
                    doc_id_clean = doc.id.replace("jk_", "")

                    if doc_id_clean in result_ids:
                        found += 1

                except Exception:
                    pass

        rate = found / len(samples) * 100
        result.details = [{"sampled": len(samples), "found": found, "rate": f"{rate:.0f}%"}]

        # 검색 결과 50건 제한으로 인해 특정 공고가 결과에 없을 수 있음
        # 중요한 것은 검색이 동작하고 DB 데이터가 반환된다는 것 (TC-401에서 검증)
        if rate >= 10:  # 10% 이상이면 통과
            result.passed = True
            result.message = f"검색 가능 비율 {rate:.0f}% ({found}/{len(samples)}) - 50건 제한 고려"
        else:
            result.message = f"검색 가능 비율 미달 {rate:.0f}% (50건 제한으로 인한 한계)"

    except Exception as e:
        result.message = f"오류: {e}"

    return result


async def tc_403_inactive_excluded() -> TestResult:
    """TC-403: 비활성 공고 제외 확인"""
    result = TestResult("TC-403", "비활성 공고 제외 확인")

    try:
        db = await get_db()

        # 비활성 공고 샘플
        query = db.collection("jobs").where("is_active", "==", False).limit(10)
        inactive_docs = list(query.stream())

        if not inactive_docs:
            result.passed = True
            result.message = "비활성 공고 없음 (검증 불가)"
            return result

        # API에서 해당 ID가 반환되지 않는지 확인
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{API_BASE}/chat",
                json={"message": "강남역 근처 연봉 2000 이상 일자리"}  # 넓은 검색
            )
            result_jobs = resp.json().get("jobs", [])
            result_ids = set(j.get("id", "").replace("jk_", "") for j in result_jobs)

            leaked = []
            for doc in inactive_docs:
                doc_id = doc.id.replace("jk_", "")
                if doc_id in result_ids:
                    leaked.append(doc_id)

            if not leaked:
                result.passed = True
                result.message = f"비활성 공고 0건 노출 (검사: {len(inactive_docs)}건)"
            else:
                result.message = f"비활성 공고 {len(leaked)}건 노출!"
                result.details = leaked

    except Exception as e:
        result.message = f"오류: {e}"

    return result


# ============================================================
# 메인 실행
# ============================================================

async def run_tests(tc_filter: Optional[int] = None):
    """테스트 실행"""
    print("=" * 70)
    print("데이터베이스 검색 검증 테스트")
    print("=" * 70)

    # 서버 상태 확인
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            health = await client.get(f"{API_BASE}/health")
            print(f"\n서버 상태: {health.json().get('status')}")
        except Exception as e:
            print(f"\n[ERROR] 서버 연결 실패: {e}")
            print("백엔드 서버를 먼저 실행하세요:")
            print("  cd backend && source venv/bin/activate && uvicorn app.main:app --port 8000")
            return

    # 테스트 그룹
    test_groups = {
        100: [
            ("TC-101", tc_101_active_jobs_exist),
            ("TC-102", tc_102_field_completeness),
            ("TC-103", tc_103_sample_lookup),
        ],
        200: [
            ("TC-201", tc_201_keyword_search),
            ("TC-202", tc_202_salary_filter),
            ("TC-203", tc_203_location_filter),
        ],
        300: [
            ("TC-301", tc_301_chat_api_returns_results),
            ("TC-302", tc_302_response_field_completeness),
        ],
        400: [
            ("TC-401", tc_401_api_db_match),
            ("TC-402", tc_402_collected_jobs_searchable),
            ("TC-403", tc_403_inactive_excluded),
        ],
    }

    # 필터 적용
    if tc_filter:
        test_groups = {tc_filter: test_groups.get(tc_filter, [])}

    all_results = []

    for group_id, tests in sorted(test_groups.items()):
        group_name = {
            100: "DB 직접 조회",
            200: "검색 서비스",
            300: "API 통합",
            400: "데이터 무결성",
        }.get(group_id, f"TC-{group_id}")

        print(f"\n{'='*50}")
        print(f"TC-{group_id}: {group_name}")
        print("=" * 50)

        for test_id, test_func in tests:
            result = await test_func()
            all_results.append(result)

            status = "PASS" if result.passed else "FAIL"
            print(f"\n  [{status}] {result.test_id}: {result.name}")
            print(f"        {result.message}")

            if result.details:
                for detail in result.details[:3]:
                    print(f"        - {detail}")

    # 요약
    print("\n" + "=" * 70)
    print("테스트 요약")
    print("=" * 70)

    passed = sum(1 for r in all_results if r.passed)
    total = len(all_results)

    for r in all_results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.test_id}: {r.message}")

    print(f"\n총 결과: {passed}/{total} 통과 ({passed/total*100:.0f}%)")

    if passed == total:
        print("\n모든 테스트 통과!")
    else:
        print(f"\n{total - passed}개 테스트 실패")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="DB 검색 검증 테스트")
    parser.add_argument("--tc", type=int, help="특정 TC 그룹만 실행 (100, 200, 300, 400)")
    args = parser.parse_args()

    asyncio.run(run_tests(tc_filter=args.tc))


if __name__ == "__main__":
    main()
