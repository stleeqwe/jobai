#!/usr/bin/env python3
"""
E2E 시나리오 테스트 - 유저 관점 전방위 테스트

다양한 검색 조건과 연속 대화를 통해 응답 품질을 검증합니다.
"""

import asyncio
import httpx
import json
from typing import Optional, List, Dict
from datetime import datetime

API_BASE = "http://localhost:8000"


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.message = ""
        self.response_time = 0
        self.jobs_count = 0
        self.details = {}


async def chat(client: httpx.AsyncClient, message: str, conversation_id: Optional[str] = None) -> dict:
    """채팅 API 호출"""
    payload = {"message": message}
    if conversation_id:
        payload["conversation_id"] = conversation_id

    start = datetime.now()
    response = await client.post(f"{API_BASE}/chat", json=payload, timeout=60.0)
    elapsed = (datetime.now() - start).total_seconds()

    result = response.json()
    result["_response_time"] = elapsed
    return result


async def chat_more(client: httpx.AsyncClient, conversation_id: str) -> dict:
    """더보기 API 호출"""
    response = await client.post(f"{API_BASE}/chat/more", json={"conversation_id": conversation_id}, timeout=30.0)
    return response.json()


def check_job_quality(jobs: List[Dict]) -> dict:
    """검색 결과 품질 체크"""
    if not jobs:
        return {"has_jobs": False}

    quality = {
        "has_jobs": True,
        "count": len(jobs),
        "with_company": sum(1 for j in jobs if j.get("company_name")),
        "with_location": sum(1 for j in jobs if j.get("location_full")),
        "with_station": sum(1 for j in jobs if j.get("nearest_station")),
        "with_salary": sum(1 for j in jobs if j.get("salary_text")),
    }
    quality["company_rate"] = f"{quality['with_company']/len(jobs)*100:.0f}%"
    quality["station_rate"] = f"{quality['with_station']/len(jobs)*100:.0f}%"
    return quality


async def test_scenario_1(client: httpx.AsyncClient) -> TestResult:
    """시나리오 1: 직무만 검색"""
    result = TestResult("시나리오 1: 직무만 검색")

    test_cases = [
        ("마케팅 관련 일자리 찾아줘", ["마케팅"]),
        ("프론트엔드 개발자 채용 알려줘", ["프론트엔드", "개발"]),
        ("UI/UX 디자이너 공고", ["디자인", "UI", "UX"]),
        ("데이터 분석가 자리 있어?", ["데이터"]),
    ]

    passed = 0
    details = []

    for query, expected_keywords in test_cases:
        try:
            resp = await chat(client, query)
            jobs = resp.get("jobs", [])

            # 검증
            has_jobs = len(jobs) > 0
            quality = check_job_quality(jobs)

            test_passed = has_jobs and quality.get("with_company", 0) > 0
            if test_passed:
                passed += 1

            details.append({
                "query": query,
                "passed": test_passed,
                "jobs": len(jobs),
                "response_time": f"{resp.get('_response_time', 0):.1f}s",
                "quality": quality,
            })

        except Exception as e:
            details.append({"query": query, "passed": False, "error": str(e)})

    result.passed = passed == len(test_cases)
    result.message = f"{passed}/{len(test_cases)} 통과"
    result.details = details
    return result


async def test_scenario_2(client: httpx.AsyncClient) -> TestResult:
    """시나리오 2: 직무 + 연봉 조건"""
    result = TestResult("시나리오 2: 직무 + 연봉 조건")

    test_cases = [
        ("연봉 4000만원 이상 마케팅 직무", 4000),
        ("백엔드 개발자 연봉 5천 이상", 5000),
        ("디자이너 3500 이상", 3500),
        ("기획자 연봉 4500 넘는 곳", 4500),
    ]

    passed = 0
    details = []

    for query, min_salary in test_cases:
        try:
            resp = await chat(client, query)
            jobs = resp.get("jobs", [])
            search_params = resp.get("search_params", {})

            # 연봉 조건이 반영되었는지 확인
            parsed_salary = search_params.get("salary_min", 0)

            # 결과 검증
            has_jobs = len(jobs) >= 0  # 연봉 조건이 있으면 결과가 적을 수 있음
            salary_parsed = parsed_salary is not None and parsed_salary > 0

            test_passed = salary_parsed
            if test_passed:
                passed += 1

            details.append({
                "query": query,
                "passed": test_passed,
                "expected_salary": min_salary,
                "parsed_salary": parsed_salary,
                "jobs": len(jobs),
                "response_time": f"{resp.get('_response_time', 0):.1f}s",
            })

        except Exception as e:
            details.append({"query": query, "passed": False, "error": str(e)})

    result.passed = passed >= len(test_cases) - 1  # 1개까지 실패 허용
    result.message = f"{passed}/{len(test_cases)} 통과"
    result.details = details
    return result


async def test_scenario_3(client: httpx.AsyncClient) -> TestResult:
    """시나리오 3: 직무 + 통근 기준점"""
    result = TestResult("시나리오 3: 직무 + 통근 기준점")

    test_cases = [
        ("강남역 근처 마케팅 일자리", "강남역"),
        ("홍대입구역 부근 디자이너", "홍대입구역"),
        ("판교역에서 가까운 개발자 공고", "판교"),
        ("을지로역 근처 기획자", "을지로"),
    ]

    passed = 0
    details = []

    for query, expected_origin in test_cases:
        try:
            resp = await chat(client, query)
            jobs = resp.get("jobs", [])
            search_params = resp.get("search_params", {})

            # 통근 기준점이 파싱되었는지 확인
            commute_origin = search_params.get("commute_origin", "")

            # 통근 시간이 계산되었는지 확인
            has_commute = any(j.get("commute_minutes") for j in jobs) if jobs else False

            test_passed = bool(commute_origin)
            if test_passed:
                passed += 1

            details.append({
                "query": query,
                "passed": test_passed,
                "expected_origin": expected_origin,
                "parsed_origin": commute_origin,
                "has_commute_time": has_commute,
                "jobs": len(jobs),
                "response_time": f"{resp.get('_response_time', 0):.1f}s",
            })

        except Exception as e:
            details.append({"query": query, "passed": False, "error": str(e)})

    result.passed = passed >= len(test_cases) - 1
    result.message = f"{passed}/{len(test_cases)} 통과"
    result.details = details
    return result


async def test_scenario_4(client: httpx.AsyncClient) -> TestResult:
    """시나리오 4: 복합 조건 (직무 + 연봉 + 통근)"""
    result = TestResult("시나리오 4: 복합 조건")

    test_cases = [
        "강남역에서 1시간 이내, 연봉 4000 이상 마케팅",
        "홍대입구역 근처 연봉 5천만원 이상 프론트엔드 개발자",
        "을지로역 부근 디자이너 연봉 3500 이상",
        "신림역에서 가까운 백엔드 개발 연봉 4500",
    ]

    passed = 0
    details = []

    for query in test_cases:
        try:
            resp = await chat(client, query)
            jobs = resp.get("jobs", [])
            search_params = resp.get("search_params", {})

            # 모든 조건이 파싱되었는지 확인
            has_keywords = bool(search_params.get("job_keywords"))
            has_salary = search_params.get("salary_min") is not None and search_params.get("salary_min", 0) > 0
            has_origin = bool(search_params.get("commute_origin"))

            test_passed = has_keywords and (has_salary or has_origin)
            if test_passed:
                passed += 1

            details.append({
                "query": query,
                "passed": test_passed,
                "params": search_params,
                "jobs": len(jobs),
                "response_time": f"{resp.get('_response_time', 0):.1f}s",
            })

        except Exception as e:
            details.append({"query": query, "passed": False, "error": str(e)})

    result.passed = passed >= len(test_cases) - 1
    result.message = f"{passed}/{len(test_cases)} 통과"
    result.details = details
    return result


async def test_scenario_5(client: httpx.AsyncClient) -> TestResult:
    """시나리오 5: 연속 대화 품질"""
    result = TestResult("시나리오 5: 연속 대화")

    conversation_flow = [
        "마케팅 일자리 찾아줘",
        "연봉 4000 이상으로 좁혀줘",
        "강남역 근처로만 보여줘",
        "더보기",  # 더보기 테스트
    ]

    details = []
    conversation_id = None
    all_passed = True

    for i, message in enumerate(conversation_flow):
        try:
            if message == "더보기" and conversation_id:
                resp = await chat_more(client, conversation_id)
            else:
                resp = await chat(client, message, conversation_id)

            # conversation_id 유지
            if not conversation_id:
                conversation_id = resp.get("conversation_id")

            jobs = resp.get("jobs", [])
            success = resp.get("success", False)

            step_passed = success
            if not step_passed:
                all_passed = False

            details.append({
                "step": i + 1,
                "message": message,
                "passed": step_passed,
                "jobs": len(jobs),
                "has_response": bool(resp.get("response")),
            })

        except Exception as e:
            details.append({"step": i + 1, "message": message, "passed": False, "error": str(e)})
            all_passed = False

    result.passed = all_passed
    result.message = f"{'통과' if all_passed else '실패'} - {len(conversation_flow)}단계 대화"
    result.details = details
    return result


async def test_scenario_6(client: httpx.AsyncClient) -> TestResult:
    """시나리오 6: 엣지 케이스"""
    result = TestResult("시나리오 6: 엣지 케이스")

    test_cases = [
        ("안녕", "인사 - 검색 없이 응답"),
        ("ㅎㅇ", "짧은 입력"),
        ("일자리", "모호한 검색어"),
        ("서울에서 일하고 싶어요", "직무 미지정"),
        ("연봉 1억 개발자", "높은 연봉 조건"),
        ("부산 마케팅", "서울 외 지역 - 결과 없음 예상"),
    ]

    passed = 0
    details = []

    for query, description in test_cases:
        try:
            resp = await chat(client, query)

            # 에러 없이 응답했는지 확인
            success = resp.get("success", False)
            has_response = bool(resp.get("response"))

            test_passed = success or has_response
            if test_passed:
                passed += 1

            details.append({
                "query": query,
                "description": description,
                "passed": test_passed,
                "success": success,
                "jobs": len(resp.get("jobs", [])),
                "response_preview": resp.get("response", "")[:100] + "..." if resp.get("response") else "",
            })

        except Exception as e:
            details.append({"query": query, "description": description, "passed": False, "error": str(e)})

    result.passed = passed >= len(test_cases) - 2  # 2개까지 실패 허용
    result.message = f"{passed}/{len(test_cases)} 통과"
    result.details = details
    return result


async def run_all_tests():
    """모든 테스트 실행"""
    print("=" * 70)
    print("E2E 시나리오 테스트 시작")
    print("=" * 70)

    async with httpx.AsyncClient() as client:
        # 서버 상태 확인
        try:
            health = await client.get(f"{API_BASE}/health")
            print(f"\n서버 상태: {health.json().get('status')}")
        except Exception as e:
            print(f"\n[ERROR] 서버 연결 실패: {e}")
            return

        # 테스트 실행
        tests = [
            test_scenario_1,
            test_scenario_2,
            test_scenario_3,
            test_scenario_4,
            test_scenario_5,
            test_scenario_6,
        ]

        results = []
        for test_func in tests:
            print(f"\n{'='*50}")
            result = await test_func(client)
            results.append(result)

            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"{status} {result.name}: {result.message}")

            for detail in result.details:
                if isinstance(detail, dict):
                    query = detail.get("query") or detail.get("message", "")
                    passed = "✓" if detail.get("passed") else "✗"
                    jobs = detail.get("jobs", "?")
                    extra = ""

                    if detail.get("parsed_salary"):
                        extra = f" (연봉: {detail['parsed_salary']})"
                    if detail.get("parsed_origin"):
                        extra = f" (위치: {detail['parsed_origin']})"
                    if detail.get("error"):
                        extra = f" [ERROR: {detail['error']}]"

                    print(f"  {passed} \"{query[:30]}...\" → {jobs}건{extra}")

        # 요약
        print("\n" + "=" * 70)
        print("테스트 요약")
        print("=" * 70)

        total_passed = sum(1 for r in results if r.passed)
        total_tests = len(results)

        for r in results:
            status = "✅" if r.passed else "❌"
            print(f"  {status} {r.name}: {r.message}")

        print(f"\n총 결과: {total_passed}/{total_tests} 시나리오 통과")

        if total_passed == total_tests:
            print("\n🎉 모든 테스트 통과!")
        else:
            print(f"\n⚠️ {total_tests - total_passed}개 시나리오 실패")

        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
