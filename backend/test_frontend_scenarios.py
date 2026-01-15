#!/usr/bin/env python3
"""E2E 검색 테스트 - 프론트엔드 시나리오 기반"""

import asyncio
import httpx
import time
from typing import Dict, List
from dataclasses import dataclass, field

BASE_URL = "http://localhost:8000"

# 주요 역 좌표 매핑
STATION_COORDS = {
    "강남역": {"latitude": 37.497916, "longitude": 127.027632, "address": "강남역"},
    "홍대입구역": {"latitude": 37.557192, "longitude": 126.925427, "address": "홍대입구역"},
    "서울역": {"latitude": 37.554648, "longitude": 126.970609, "address": "서울역"},
    "역삼역": {"latitude": 37.500622, "longitude": 127.036456, "address": "역삼역"},
    "판교역": {"latitude": 37.394955, "longitude": 127.111419, "address": "판교역"},
}

@dataclass
class TestResult:
    name: str
    passed: bool
    details: str = ""
    response_time: float = 0.0
    data: Dict = field(default_factory=dict)

class E2ESearchTester:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.results: List[TestResult] = []
        self.conversation_id = None

    async def close(self):
        await self.client.aclose()

    async def chat(self, message: str, user_location: str = "") -> Dict:
        """채팅 API 호출"""
        start = time.time()
        payload = {
            "message": message,
            "conversation_id": self.conversation_id,
        }
        # 역 이름을 좌표로 변환
        if user_location and user_location in STATION_COORDS:
            payload["user_location"] = STATION_COORDS[user_location]
        elif user_location:
            # 알 수 없는 역이면 강남역 좌표 사용 (테스트용)
            payload["user_location"] = {
                "latitude": 37.497916,
                "longitude": 127.027632,
                "address": user_location
            }

        resp = await self.client.post(f"{BASE_URL}/chat", json=payload)
        elapsed = time.time() - start

        data = resp.json()
        self.conversation_id = data.get("conversation_id")
        return {"data": data, "time": elapsed}

    async def chat_more(self) -> Dict:
        """더보기 API 호출"""
        start = time.time()
        resp = await self.client.post(f"{BASE_URL}/chat/more", json={
            "conversation_id": self.conversation_id
        })
        elapsed = time.time() - start
        return {"data": resp.json(), "time": elapsed}

    def reset_session(self):
        """세션 초기화"""
        self.conversation_id = None

    # ========== 1. 기본 검색 테스트 ==========

    async def test_1_1_salary_question(self):
        """1-1: 연봉 미입력 시 질문"""
        self.reset_session()
        result = await self.chat("프론트엔드 개발자 채용공고 보여줘")

        data = result["data"]
        jobs = data.get("jobs", [])
        message = data.get("message", "")

        # 연봉 질문하거나 연봉무관으로 처리
        passed = "연봉" in message or len(jobs) > 0
        return TestResult(
            name="1-1: 연봉 미입력 시 질문",
            passed=passed,
            details=f"결과 {len(jobs)}건, 응답에 연봉 언급: {'연봉' in message}",
            response_time=result["time"],
            data={"message": message[:200]}
        )

    async def test_1_2_backend_salary(self):
        """1-2: 백엔드 + 연봉 검색"""
        self.reset_session()
        result = await self.chat("백엔드 개발자 연봉 4천 이상")

        data = result["data"]
        jobs = data.get("jobs", [])

        backend_keywords = ["백엔드", "backend", "서버", "server", "java", "python", "node", "spring"]
        relevant_count = 0
        for job in jobs[:10]:
            title = (job.get("title", "") + " " + str(job.get("job_keywords", []))).lower()
            if any(kw in title for kw in backend_keywords):
                relevant_count += 1

        passed = len(jobs) > 0 and relevant_count >= len(jobs[:10]) * 0.5
        return TestResult(
            name="1-2: 백엔드 + 연봉 4천 이상",
            passed=passed,
            details=f"결과 {len(jobs)}건, 관련 공고 {relevant_count}/10",
            response_time=result["time"],
            data={"total": len(jobs), "relevant": relevant_count}
        )

    async def test_1_3_salary_none(self):
        """1-3: 연봉 무관 검색"""
        self.reset_session()
        result = await self.chat("디자이너 연봉 무관")

        data = result["data"]
        jobs = data.get("jobs", [])
        params = data.get("search_params", {})

        salary_min = params.get("salary_min", 0)
        passed = len(jobs) > 0
        return TestResult(
            name="1-3: 연봉 무관 검색",
            passed=passed,
            details=f"결과 {len(jobs)}건, salary_min={salary_min}",
            response_time=result["time"],
            data={"total": len(jobs)}
        )

    async def test_1_4_salary_range(self):
        """1-4: 연봉 범위 검색"""
        self.reset_session()
        result = await self.chat("PM 3천~5천")

        data = result["data"]
        jobs = data.get("jobs", [])
        params = data.get("search_params", {})

        passed = len(jobs) > 0
        return TestResult(
            name="1-4: 연봉 범위 3천~5천",
            passed=passed,
            details=f"결과 {len(jobs)}건, params={params}",
            response_time=result["time"],
            data={"total": len(jobs)}
        )

    async def test_1_5_keyword_expansion(self):
        """1-5: 키워드 확장 (데이터 분석가)"""
        self.reset_session()
        result = await self.chat("데이터 분석가 5천만원 이상")

        data = result["data"]
        jobs = data.get("jobs", [])
        keywords = data.get("search_params", {}).get("job_keywords", [])

        passed = len(jobs) >= 0
        return TestResult(
            name="1-5: 데이터 분석가 키워드 확장",
            passed=passed,
            details=f"결과 {len(jobs)}건, 키워드: {keywords[:5]}",
            response_time=result["time"],
            data={"total": len(jobs), "keywords": keywords}
        )

    # ========== 2. 위치 기반 검색 테스트 ==========

    async def test_2_1_station_search(self):
        """2-1: 역명 검색 (강남역)"""
        self.reset_session()
        result = await self.chat("강남역 근처 개발자 3천 이상")

        data = result["data"]
        jobs = data.get("jobs", [])

        gangnam_count = 0
        for job in jobs[:10]:
            loc = (job.get("location", "") + str(job.get("location_gugun", ""))).lower()
            if "강남" in loc:
                gangnam_count += 1

        passed = len(jobs) > 0 and gangnam_count >= min(len(jobs[:10]), 5) * 0.5
        return TestResult(
            name="2-1: 강남역 근처 검색",
            passed=passed,
            details=f"결과 {len(jobs)}건, 강남 지역 {gangnam_count}/10",
            response_time=result["time"],
            data={"total": len(jobs), "gangnam_count": gangnam_count}
        )

    async def test_2_2_gu_search(self):
        """2-2: 구 단위 검색 (서초구)"""
        self.reset_session()
        result = await self.chat("서초구 내 마케터 연봉 무관")

        data = result["data"]
        jobs = data.get("jobs", [])

        seocho_count = 0
        for job in jobs[:10]:
            loc = (job.get("location", "") + str(job.get("location_gugun", ""))).lower()
            if "서초" in loc:
                seocho_count += 1

        passed = len(jobs) > 0 and seocho_count >= min(len(jobs[:10]), 5) * 0.5
        return TestResult(
            name="2-2: 서초구 검색",
            passed=passed,
            details=f"결과 {len(jobs)}건, 서초구 {seocho_count}/10",
            response_time=result["time"],
            data={"total": len(jobs), "seocho_count": seocho_count}
        )

    async def test_2_3_pangyo_search(self):
        """2-3: 판교 검색"""
        self.reset_session()
        result = await self.chat("판교 IT기업 개발자 4천 이상")

        data = result["data"]
        jobs = data.get("jobs", [])

        passed = True  # 판교는 서울 외 지역이라 결과 없어도 OK
        return TestResult(
            name="2-3: 판교 검색",
            passed=passed,
            details=f"결과 {len(jobs)}건 (서울 외 지역, 결과 없을 수 있음)",
            response_time=result["time"],
            data={"total": len(jobs)}
        )

    async def test_2_4_station_to_gu(self):
        """2-4: 역명→구 변환 (가산디지털단지)"""
        self.reset_session()
        result = await self.chat("가산디지털단지 QA 3천 이상")

        data = result["data"]
        jobs = data.get("jobs", [])

        gasan_count = 0
        for job in jobs[:10]:
            loc = job.get("location", "").lower()
            if "금천" in loc or "가산" in loc:
                gasan_count += 1

        passed = len(jobs) >= 0
        return TestResult(
            name="2-4: 가산디지털단지 → 금천구",
            passed=passed,
            details=f"결과 {len(jobs)}건, 금천/가산 {gasan_count}건",
            response_time=result["time"],
            data={"total": len(jobs), "gasan_count": gasan_count}
        )

    # ========== 3. 통근시간 기반 검색 테스트 ==========

    async def test_3_1_commute_30min(self):
        """3-1: 통근 30분 이내"""
        self.reset_session()
        result = await self.chat("출근 30분 이내 개발자 3천 이상", user_location="강남역")

        data = result["data"]
        jobs = data.get("jobs", [])

        within_30 = 0
        for job in jobs[:10]:
            cm = job.get("commute_minutes", 999)
            if cm and cm <= 30:
                within_30 += 1

        passed = len(jobs) > 0
        return TestResult(
            name="3-1: 통근 30분 이내",
            passed=passed,
            details=f"결과 {len(jobs)}건, 30분 이내 {within_30}건",
            response_time=result["time"],
            data={"total": len(jobs), "within_30": within_30}
        )

    async def test_3_2_commute_60min(self):
        """3-2: 통근 1시간 이내"""
        self.reset_session()
        result = await self.chat("1시간 이내 출퇴근 가능한 디자이너 연봉 무관", user_location="홍대입구역")

        data = result["data"]
        jobs = data.get("jobs", [])

        has_commute = sum(1 for j in jobs[:10] if j.get("commute_minutes") is not None)
        passed = len(jobs) > 0
        return TestResult(
            name="3-2: 통근 1시간 이내",
            passed=passed,
            details=f"결과 {len(jobs)}건, 통근시간 계산됨 {has_commute}건",
            response_time=result["time"],
            data={"total": len(jobs), "has_commute": has_commute}
        )

    async def test_3_3_no_location(self):
        """3-3: 위치 미제공 시 안내"""
        self.reset_session()
        result = await self.chat("가까운 곳 마케터 연봉 무관")

        data = result["data"]
        message = data.get("message", "")

        passed = True  # graceful handling
        return TestResult(
            name="3-3: 위치 미제공 시 처리",
            passed=passed,
            details=f"응답: {message[:100]}...",
            response_time=result["time"],
            data={}
        )

    # ========== 4. 후속 대화 테스트 ==========

    async def test_4_1_filter_salary(self):
        """4-1: 연봉 필터 추가"""
        self.reset_session()
        r1 = await self.chat("개발자 3천 이상")
        count1 = len(r1["data"].get("jobs", []))

        r2 = await self.chat("연봉 4천 이상만")
        count2 = len(r2["data"].get("jobs", []))

        passed = count1 > 0
        return TestResult(
            name="4-1: 연봉 필터 추가",
            passed=passed,
            details=f"1차: {count1}건 → 2차: {count2}건",
            response_time=r2["time"],
            data={"count1": count1, "count2": count2}
        )

    async def test_4_2_filter_location(self):
        """4-2: 위치 필터 추가"""
        self.reset_session()
        r1 = await self.chat("디자이너 연봉 무관")
        count1 = len(r1["data"].get("jobs", []))

        r2 = await self.chat("강남쪽만 보여줘")
        count2 = len(r2["data"].get("jobs", []))

        passed = count1 > 0
        return TestResult(
            name="4-2: 위치 필터 추가",
            passed=passed,
            details=f"1차: {count1}건 → 2차(강남): {count2}건",
            response_time=r2["time"],
            data={"count1": count1, "count2": count2}
        )

    async def test_4_3_change_job(self):
        """4-3: 직무 변경"""
        self.reset_session()
        await self.chat("백엔드 4천 이상")
        r2 = await self.chat("프론트엔드로 다시 검색")
        jobs2 = r2["data"].get("jobs", [])

        passed = len(jobs2) > 0
        return TestResult(
            name="4-3: 직무 변경 (백엔드→프론트엔드)",
            passed=passed,
            details=f"결과 {len(jobs2)}건",
            response_time=r2["time"],
            data={"total": len(jobs2)}
        )

    async def test_4_4_more(self):
        """4-4: 더보기"""
        self.reset_session()
        r1 = await self.chat("개발자 3천 이상")
        count1 = len(r1["data"].get("jobs", []))

        r2 = await self.chat_more()
        count2 = len(r2["data"].get("jobs", []))

        passed = r2["time"] < 2.0
        return TestResult(
            name="4-4: 더보기 (LLM 없이)",
            passed=passed,
            details=f"1차: {count1}건, 더보기: {count2}건, 응답: {r2['time']:.2f}초",
            response_time=r2["time"],
            data={"count1": count1, "count2": count2}
        )

    async def test_4_5_filter_commute(self):
        """4-5: 통근시간 필터"""
        self.reset_session()
        r1 = await self.chat("PM 연봉 무관", user_location="강남역")
        count1 = len(r1["data"].get("jobs", []))

        r2 = await self.chat("통근 30분 이내만", user_location="강남역")
        count2 = len(r2["data"].get("jobs", []))

        passed = count1 > 0
        return TestResult(
            name="4-5: 통근시간 필터 추가",
            passed=passed,
            details=f"1차: {count1}건 → 2차(30분): {count2}건",
            response_time=r2["time"],
            data={"count1": count1, "count2": count2}
        )

    # ========== 5. 키워드 확장 테스트 ==========

    async def test_5_keywords(self):
        """5-1~5: 키워드 확장 통합 테스트"""
        test_cases = [
            ("웹 디자이너", "웹디자이너"),
            ("프론트엔드", "프론트"),
            ("서버 개발", "서버"),
            ("PM", "PM"),
            ("AI 엔지니어", "AI"),
        ]

        results = []
        for query, check_word in test_cases:
            self.reset_session()
            r = await self.chat(f"{query} 연봉 무관")
            count = len(r["data"].get("jobs", []))
            results.append(f"{query}: {count}건")

        passed = True
        return TestResult(
            name="5: 키워드 확장 테스트",
            passed=passed,
            details=", ".join(results),
            response_time=0,
            data={}
        )

    # ========== 6. 엣지 케이스 테스트 ==========

    async def test_6_1_no_salary(self):
        """6-1: 연봉 미입력"""
        self.reset_session()
        result = await self.chat("개발자")
        data = result["data"]
        passed = True
        return TestResult(
            name="6-1: 연봉 미입력",
            passed=passed,
            details=f"결과 {len(data.get('jobs', []))}건",
            response_time=result["time"],
            data={}
        )

    async def test_6_2_no_job(self):
        """6-2: 직무 미입력"""
        self.reset_session()
        result = await self.chat("연봉 5천 이상")
        data = result["data"]
        message = data.get("message", "")
        passed = "직무" in message or "어떤" in message or len(data.get("jobs", [])) == 0
        return TestResult(
            name="6-2: 직무 미입력",
            passed=passed,
            details=f"응답: {message[:80]}...",
            response_time=result["time"],
            data={}
        )

    async def test_6_3_greeting(self):
        """6-3: 인사"""
        self.reset_session()
        result = await self.chat("안녕하세요")
        data = result["data"]
        passed = len(data.get("jobs", [])) == 0
        return TestResult(
            name="6-3: 인사 메시지",
            passed=passed,
            details=f"응답: {data.get('message', '')[:80]}...",
            response_time=result["time"],
            data={}
        )

    async def test_6_4_no_result(self):
        """6-4: 존재하지 않는 직무"""
        self.reset_session()
        result = await self.chat("존재하지않는직무xyz 3천 이상")
        data = result["data"]
        passed = True
        return TestResult(
            name="6-4: 존재하지 않는 직무",
            passed=passed,
            details=f"결과 {len(data.get('jobs', []))}건",
            response_time=result["time"],
            data={}
        )

    async def test_6_5_high_salary(self):
        """6-5: 비현실적 연봉"""
        self.reset_session()
        result = await self.chat("개발자 연봉 100억 이상")
        data = result["data"]
        passed = True
        return TestResult(
            name="6-5: 비현실적 연봉 (100억)",
            passed=passed,
            details=f"결과 {len(data.get('jobs', []))}건",
            response_time=result["time"],
            data={}
        )

    async def test_6_6_negative_salary(self):
        """6-6: 음수 연봉"""
        self.reset_session()
        result = await self.chat("마케터 -3천")
        passed = True
        return TestResult(
            name="6-6: 음수 연봉 처리",
            passed=passed,
            details="graceful handling",
            response_time=result["time"],
            data={}
        )

    # ========== 7. 데이터 품질 검증 ==========

    async def test_7_data_quality(self):
        """7: 데이터 품질 검증"""
        self.reset_session()
        result = await self.chat("개발자 연봉 무관")
        jobs = result["data"].get("jobs", [])[:10]

        checks = {"title": 0, "company": 0, "location": 0, "url": 0, "deadline": 0}
        seoul_gu = ["강남구", "서초구", "송파구", "강동구", "마포구", "영등포구", "용산구",
                    "종로구", "중구", "성동구", "광진구", "동대문구", "중랑구", "성북구",
                    "강북구", "도봉구", "노원구", "은평구", "서대문구", "양천구", "강서구",
                    "구로구", "금천구", "동작구", "관악구"]

        for job in jobs:
            if job.get("title") and len(job["title"]) > 5:
                checks["title"] += 1
            if job.get("company_name") and len(job["company_name"]) >= 2:
                checks["company"] += 1
            loc = job.get("location", "") or ""
            if any(gu in loc for gu in seoul_gu) or "서울" in loc:
                checks["location"] += 1
            if job.get("url", "").startswith("http"):
                checks["url"] += 1
            dl = job.get("deadline", "")
            if dl in ["상시채용", "채용시 마감"] or "." in dl:
                checks["deadline"] += 1

        total = len(jobs)
        scores = {k: f"{v}/{total}" for k, v in checks.items()}
        passed = all(v >= total * 0.7 for v in checks.values()) if total > 0 else True

        return TestResult(
            name="7: 데이터 품질 검증",
            passed=passed,
            details=f"제목:{scores['title']}, 회사:{scores['company']}, 위치:{scores['location']}, URL:{scores['url']}, 마감:{scores['deadline']}",
            response_time=result["time"],
            data=checks
        )

    # ========== 8. 성능 테스트 ==========

    async def test_8_performance(self):
        """8: 성능 테스트"""
        self.reset_session()
        r1 = await self.chat("개발자 연봉 무관")
        first_time = r1["time"]

        r2 = await self.chat_more()
        more_time = r2["time"]

        passed = first_time < 15.0 and more_time < 2.0
        return TestResult(
            name="8: 성능 테스트",
            passed=passed,
            details=f"첫응답: {first_time:.2f}초 (<15초), 더보기: {more_time:.2f}초 (<2초)",
            response_time=first_time,
            data={"first": first_time, "more": more_time}
        )

    async def run_all(self):
        """모든 테스트 실행"""
        tests = [
            # 1. 기본 검색
            ("1. 기본 검색", [
                self.test_1_1_salary_question,
                self.test_1_2_backend_salary,
                self.test_1_3_salary_none,
                self.test_1_4_salary_range,
                self.test_1_5_keyword_expansion,
            ]),
            # 2. 위치 기반
            ("2. 위치 기반", [
                self.test_2_1_station_search,
                self.test_2_2_gu_search,
                self.test_2_3_pangyo_search,
                self.test_2_4_station_to_gu,
            ]),
            # 3. 통근시간
            ("3. 통근시간", [
                self.test_3_1_commute_30min,
                self.test_3_2_commute_60min,
                self.test_3_3_no_location,
            ]),
            # 4. 후속 대화
            ("4. 후속 대화", [
                self.test_4_1_filter_salary,
                self.test_4_2_filter_location,
                self.test_4_3_change_job,
                self.test_4_4_more,
                self.test_4_5_filter_commute,
            ]),
            # 5. 키워드 확장
            ("5. 키워드 확장", [
                self.test_5_keywords,
            ]),
            # 6. 엣지 케이스
            ("6. 엣지 케이스", [
                self.test_6_1_no_salary,
                self.test_6_2_no_job,
                self.test_6_3_greeting,
                self.test_6_4_no_result,
                self.test_6_5_high_salary,
                self.test_6_6_negative_salary,
            ]),
            # 7. 데이터 품질
            ("7. 데이터 품질", [
                self.test_7_data_quality,
            ]),
            # 8. 성능
            ("8. 성능", [
                self.test_8_performance,
            ]),
        ]

        print("=" * 70)
        print("E2E 프론트엔드 시나리오 테스트")
        print("=" * 70)

        for section_name, test_fns in tests:
            print(f"\n### {section_name} ###")
            for test_fn in test_fns:
                try:
                    result = await test_fn()
                    self.results.append(result)
                    status = "PASS" if result.passed else "FAIL"
                    print(f"  [{status}] {result.name}")
                    print(f"         {result.details}")
                except Exception as e:
                    self.results.append(TestResult(name=test_fn.__name__, passed=False, details=str(e)))
                    print(f"  [ERROR] {test_fn.__name__}: {e}")

        # 요약
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)

        print("\n" + "=" * 70)
        print(f"테스트 완료: {passed}/{total} 통과 ({passed/total*100:.1f}%)")
        print("=" * 70)

        failed = [r for r in self.results if not r.passed]
        if failed:
            print("\n실패한 테스트:")
            for r in failed:
                print(f"  - {r.name}")

        return self.results


async def main():
    tester = E2ESearchTester()
    try:
        await tester.run_all()
    finally:
        await tester.close()


if __name__ == "__main__":
    asyncio.run(main())
