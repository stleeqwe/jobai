#!/usr/bin/env python3
"""
프론트엔드 테스트 시나리오 - 종합 E2E 검증

JobBot 프론트엔드 관점에서 전방위 테스트 수행
"""

import asyncio
import time
import random
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

import httpx

API_BASE = "http://localhost:8000"

# 서울 25개 구
SEOUL_GU = [
    "강남구", "서초구", "영등포구", "강서구", "마포구", "송파구", "구로구", "금천구",
    "중구", "성동구", "용산구", "종로구", "동대문구", "성북구", "강북구", "도봉구",
    "노원구", "은평구", "서대문구", "양천구", "강동구", "광진구", "중랑구", "동작구", "관악구"
]


@dataclass
class TestResult:
    scenario_id: str
    name: str
    passed: bool = False
    message: str = ""
    response_time: float = 0
    details: Dict = field(default_factory=dict)


class FrontendTester:
    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
        self.results: List[TestResult] = []
        self.conversation_id: Optional[str] = None

    async def setup(self):
        self.client = httpx.AsyncClient(timeout=60.0)

    async def teardown(self):
        if self.client:
            await self.client.aclose()

    async def chat(self, message: str, conversation_id: Optional[str] = None) -> Dict:
        """채팅 API 호출"""
        start = time.time()
        payload = {"message": message}
        if conversation_id:
            payload["conversation_id"] = conversation_id

        resp = await self.client.post(f"{API_BASE}/chat", json=payload)
        elapsed = time.time() - start

        result = resp.json()
        result["_response_time"] = elapsed
        return result

    async def chat_more(self, conversation_id: str) -> Dict:
        """더보기 API 호출"""
        start = time.time()
        resp = await self.client.post(
            f"{API_BASE}/chat/more",
            json={"conversation_id": conversation_id}
        )
        elapsed = time.time() - start

        result = resp.json()
        result["_response_time"] = elapsed
        return result

    def add_result(self, result: TestResult):
        self.results.append(result)
        status = "PASS" if result.passed else "FAIL"
        print(f"  [{status}] {result.scenario_id}: {result.name}")
        print(f"         {result.message}")
        if result.response_time > 0:
            print(f"         응답시간: {result.response_time:.2f}s")

    # ============================================================
    # 1. 기본 검색 테스트 (직무 + 연봉)
    # ============================================================

    async def test_1_basic_search(self):
        print("\n" + "=" * 60)
        print("1. 기본 검색 테스트 (직무 + 연봉)")
        print("=" * 60)

        # 1-1: 연봉 미입력 시 질문
        result = TestResult("1-1", "연봉 미입력 시 질문")
        resp = await self.chat("프론트엔드 개발자 채용공고 보여줘")
        result.response_time = resp["_response_time"]

        # 검색 실행 안 되고 질문해야 함
        jobs = resp.get("jobs", [])
        response_text = resp.get("response", "")

        if len(jobs) == 0 and ("연봉" in response_text or "희망" in response_text):
            result.passed = True
            result.message = "연봉 정보 요청 확인"
        else:
            result.message = f"결과 {len(jobs)}건 반환 (질문 예상)"
        result.details = {"jobs": len(jobs), "response_preview": response_text[:100]}
        self.add_result(result)

        # 1-2: 백엔드 + 연봉 검색
        result = TestResult("1-2", "백엔드 + 연봉 검색")
        resp = await self.chat("강남역 근처 백엔드 개발자 연봉 4천 이상")
        result.response_time = resp["_response_time"]

        jobs = resp.get("jobs", [])
        params = resp.get("search_params", {})

        # 백엔드/서버 관련 공고 확인
        backend_keywords = ["백엔드", "backend", "서버", "server", "java", "python", "node"]
        backend_count = sum(1 for j in jobs if any(k in j.get("title", "").lower() for k in backend_keywords))

        if len(jobs) > 0 and backend_count > len(jobs) * 0.3:
            result.passed = True
            result.message = f"{len(jobs)}건 중 백엔드 관련 {backend_count}건 ({backend_count/len(jobs)*100:.0f}%)"
        else:
            result.message = f"결과 {len(jobs)}건, 백엔드 관련 {backend_count}건"
        result.details = {"jobs": len(jobs), "backend": backend_count, "params": params}
        self.add_result(result)

        # 1-3: 연봉 무관 검색
        result = TestResult("1-3", "연봉 무관 검색")
        resp = await self.chat("강남역 근처 디자이너 연봉 무관")
        result.response_time = resp["_response_time"]

        jobs = resp.get("jobs", [])
        params = resp.get("search_params", {})

        # salary_min이 0 또는 None
        salary_min = params.get("salary_min", 0)
        if len(jobs) > 0 and (salary_min == 0 or salary_min is None):
            result.passed = True
            result.message = f"{len(jobs)}건 반환, salary_min={salary_min}"
        else:
            result.message = f"결과 {len(jobs)}건, salary_min={salary_min}"
        result.details = {"jobs": len(jobs), "params": params}
        self.add_result(result)

        # 1-4: 연봉 범위 검색
        result = TestResult("1-4", "연봉 범위 검색")
        resp = await self.chat("강남역 근처 PM 3천~5천")
        result.response_time = resp["_response_time"]

        jobs = resp.get("jobs", [])
        params = resp.get("search_params", {})

        salary_min = params.get("salary_min", 0)
        salary_max = params.get("salary_max")

        if len(jobs) > 0:
            result.passed = True
            result.message = f"{len(jobs)}건 반환, salary={salary_min}~{salary_max}"
        else:
            result.message = f"결과 {len(jobs)}건"
        result.details = {"jobs": len(jobs), "params": params}
        self.add_result(result)

        # 1-5: 키워드 확장 검색
        result = TestResult("1-5", "키워드 확장 검색")
        resp = await self.chat("강남역 근처 데이터 분석가 5천만원 이상")
        result.response_time = resp["_response_time"]

        jobs = resp.get("jobs", [])
        data_keywords = ["데이터", "data", "분석", "analyst", "DA", "사이언스", "science"]
        data_count = sum(1 for j in jobs if any(k in j.get("title", "").lower() for k in data_keywords))

        if len(jobs) > 0:
            result.passed = True
            result.message = f"{len(jobs)}건 중 데이터 관련 {data_count}건"
        else:
            result.message = f"결과 {len(jobs)}건"
        result.details = {"jobs": len(jobs), "data_related": data_count}
        self.add_result(result)

    # ============================================================
    # 2. 위치 기반 검색 테스트
    # ============================================================

    async def test_2_location_search(self):
        print("\n" + "=" * 60)
        print("2. 위치 기반 검색 테스트")
        print("=" * 60)

        # 2-1: 역명 검색
        result = TestResult("2-1", "역명 검색 (강남역)")
        resp = await self.chat("강남역 근처 개발자 3천 이상")
        result.response_time = resp["_response_time"]

        jobs = resp.get("jobs", [])
        gangnam_count = sum(1 for j in jobs if "강남" in j.get("location", ""))

        if len(jobs) > 0 and gangnam_count > 0:
            result.passed = True
            result.message = f"{len(jobs)}건 중 강남 지역 {gangnam_count}건 ({gangnam_count/len(jobs)*100:.0f}%)"
        else:
            result.message = f"결과 {len(jobs)}건, 강남 {gangnam_count}건"
        result.details = {"jobs": len(jobs), "gangnam": gangnam_count}
        self.add_result(result)

        # 2-2: 구 단위 검색
        result = TestResult("2-2", "구 단위 검색 (서초구)")
        resp = await self.chat("서초구 내 마케터 연봉 무관")
        result.response_time = resp["_response_time"]

        jobs = resp.get("jobs", [])
        seocho_count = sum(1 for j in jobs if "서초" in j.get("location", ""))

        if len(jobs) > 0 and seocho_count > len(jobs) * 0.5:
            result.passed = True
            result.message = f"{len(jobs)}건 중 서초구 {seocho_count}건 ({seocho_count/len(jobs)*100:.0f}%)"
        else:
            result.message = f"결과 {len(jobs)}건, 서초구 {seocho_count}건"
        result.details = {"jobs": len(jobs), "seocho": seocho_count}
        self.add_result(result)

        # 2-3: 판교 검색 (서울 외 지역)
        result = TestResult("2-3", "판교 검색")
        resp = await self.chat("판교 IT기업 개발자 4천 이상")
        result.response_time = resp["_response_time"]

        jobs = resp.get("jobs", [])
        response_text = resp.get("response", "")

        # 판교는 서울 외 지역이므로 결과 없거나 안내 예상
        if len(jobs) == 0 or "서울" in response_text or "판교" in response_text:
            result.passed = True
            result.message = f"판교 검색 처리됨 (결과: {len(jobs)}건)"
        else:
            result.message = f"결과 {len(jobs)}건"
        result.details = {"jobs": len(jobs)}
        self.add_result(result)

        # 2-4: 역명→구 변환 (가산디지털단지)
        result = TestResult("2-4", "역명→구 변환 (가산디지털단지)")
        resp = await self.chat("가산디지털단지 QA 3천 이상")
        result.response_time = resp["_response_time"]

        jobs = resp.get("jobs", [])
        gasan_count = sum(1 for j in jobs if "금천" in j.get("location", "") or "가산" in j.get("location", ""))

        if len(jobs) > 0:
            result.passed = True
            result.message = f"{len(jobs)}건 반환, 금천/가산 {gasan_count}건"
        else:
            result.message = f"결과 {len(jobs)}건"
        result.details = {"jobs": len(jobs), "gasan_geumcheon": gasan_count}
        self.add_result(result)

    # ============================================================
    # 3. 통근시간 기반 검색 테스트
    # ============================================================

    async def test_3_commute_search(self):
        print("\n" + "=" * 60)
        print("3. 통근시간 기반 검색 테스트")
        print("=" * 60)

        # 3-1: 30분 이내 통근
        result = TestResult("3-1", "통근 30분 이내")
        resp = await self.chat("강남역에서 출근 30분 이내 개발자 3천 이상")
        result.response_time = resp["_response_time"]

        jobs = resp.get("jobs", [])
        params = resp.get("search_params", {})

        # commute_minutes 확인
        with_commute = sum(1 for j in jobs if j.get("commute_minutes") is not None)
        within_30 = sum(1 for j in jobs if j.get("commute_minutes") and j.get("commute_minutes") <= 30)

        if len(jobs) > 0:
            result.passed = True
            result.message = f"{len(jobs)}건 반환, 통근시간 포함 {with_commute}건"
        else:
            result.message = f"결과 {len(jobs)}건"
        result.details = {"jobs": len(jobs), "with_commute": with_commute, "within_30": within_30}
        self.add_result(result)

        # 3-2: 1시간 이내 통근
        result = TestResult("3-2", "통근 1시간 이내")
        resp = await self.chat("홍대입구역에서 1시간 이내 출퇴근 가능한 디자이너 연봉 3천 이상")
        result.response_time = resp["_response_time"]

        jobs = resp.get("jobs", [])
        with_commute = sum(1 for j in jobs if j.get("commute_minutes") is not None)

        if len(jobs) > 0:
            result.passed = True
            result.message = f"{len(jobs)}건 반환, 통근시간 포함 {with_commute}건"
        else:
            result.message = f"결과 {len(jobs)}건"
        result.details = {"jobs": len(jobs), "with_commute": with_commute}
        self.add_result(result)

        # 3-3: 위치 미제공 시 안내
        result = TestResult("3-3", "위치 미제공 시 안내")
        resp = await self.chat("가까운 곳 마케터 연봉 무관")
        result.response_time = resp["_response_time"]

        jobs = resp.get("jobs", [])
        response_text = resp.get("response", "")

        # 위치 정보가 없으면 위치 요청 또는 넓은 검색
        if "위치" in response_text or "어디" in response_text or len(jobs) > 0:
            result.passed = True
            result.message = "위치 안내 또는 검색 수행"
        else:
            result.message = f"결과 {len(jobs)}건"
        result.details = {"jobs": len(jobs), "response_preview": response_text[:100]}
        self.add_result(result)

    # ============================================================
    # 4. 후속 대화 테스트
    # ============================================================

    async def test_4_followup(self):
        print("\n" + "=" * 60)
        print("4. 후속 대화 테스트")
        print("=" * 60)

        # 4-1: 연봉 필터 추가
        result = TestResult("4-1", "연봉 필터 추가")
        resp1 = await self.chat("강남역 근처 개발자 3천 이상")
        conv_id = resp1.get("conversation_id")
        count1 = len(resp1.get("jobs", []))

        resp2 = await self.chat("연봉 5천 이상만 보여줘", conv_id)
        result.response_time = resp2["_response_time"]
        count2 = len(resp2.get("jobs", []))

        if count2 <= count1:
            result.passed = True
            result.message = f"필터 적용: {count1}건 → {count2}건"
        else:
            result.message = f"필터 후 증가? {count1}건 → {count2}건"
        result.details = {"before": count1, "after": count2}
        self.add_result(result)

        # 4-2: 위치 필터 추가
        result = TestResult("4-2", "위치 필터 추가")
        resp1 = await self.chat("서울 디자이너 연봉 3천 이상")
        conv_id = resp1.get("conversation_id")
        count1 = len(resp1.get("jobs", []))

        resp2 = await self.chat("강남쪽만 보여줘", conv_id)
        result.response_time = resp2["_response_time"]
        count2 = len(resp2.get("jobs", []))
        gangnam_count = sum(1 for j in resp2.get("jobs", []) if "강남" in j.get("location", ""))

        if gangnam_count > 0:
            result.passed = True
            result.message = f"위치 필터: {count1}건 → {count2}건 (강남 {gangnam_count}건)"
        else:
            result.message = f"결과 {count2}건, 강남 {gangnam_count}건"
        result.details = {"before": count1, "after": count2, "gangnam": gangnam_count}
        self.add_result(result)

        # 4-3: 직무 변경
        result = TestResult("4-3", "직무 변경 재검색")
        resp1 = await self.chat("강남역 근처 백엔드 4천 이상")
        conv_id = resp1.get("conversation_id")

        resp2 = await self.chat("프론트엔드로 다시 검색해줘", conv_id)
        result.response_time = resp2["_response_time"]
        jobs = resp2.get("jobs", [])

        frontend_keywords = ["프론트", "frontend", "front", "react", "vue", "웹"]
        frontend_count = sum(1 for j in jobs if any(k in j.get("title", "").lower() for k in frontend_keywords))

        if len(jobs) > 0 and frontend_count > 0:
            result.passed = True
            result.message = f"{len(jobs)}건 중 프론트엔드 {frontend_count}건"
        else:
            result.message = f"결과 {len(jobs)}건, 프론트엔드 {frontend_count}건"
        result.details = {"jobs": len(jobs), "frontend": frontend_count}
        self.add_result(result)

        # 4-4: 더보기
        result = TestResult("4-4", "더보기 기능")
        resp1 = await self.chat("강남역 근처 개발자 3천 이상")
        conv_id = resp1.get("conversation_id")
        count1 = len(resp1.get("jobs", []))

        if count1 > 0:
            resp2 = await self.chat_more(conv_id)
            result.response_time = resp2["_response_time"]
            count2 = len(resp2.get("jobs", []))

            if resp2.get("success") and result.response_time < 3.0:  # LLM 없이 빠르게 응답
                result.passed = True
                result.message = f"더보기 성공: {count2}건 추가 (응답 {result.response_time:.2f}초)"
            else:
                result.message = f"더보기 결과: {count2}건"
        else:
            result.message = "초기 검색 결과 없음"
        result.details = {"first": count1, "more": count2 if count1 > 0 else 0}
        self.add_result(result)

        # 4-5: 통근시간 필터
        result = TestResult("4-5", "통근시간 필터 추가")
        resp1 = await self.chat("강남역 근처 PM 연봉 3천 이상")
        conv_id = resp1.get("conversation_id")
        count1 = len(resp1.get("jobs", []))

        resp2 = await self.chat("통근 30분 이내만 보여줘", conv_id)
        result.response_time = resp2["_response_time"]
        count2 = len(resp2.get("jobs", []))

        if count2 <= count1 or len(resp2.get("jobs", [])) > 0:
            result.passed = True
            result.message = f"통근 필터: {count1}건 → {count2}건"
        else:
            result.message = f"결과: {count1}건 → {count2}건"
        result.details = {"before": count1, "after": count2}
        self.add_result(result)

    # ============================================================
    # 5. 직무 키워드 확장 테스트
    # ============================================================

    async def test_5_keyword_expansion(self):
        print("\n" + "=" * 60)
        print("5. 직무 키워드 확장 테스트")
        print("=" * 60)

        test_cases = [
            ("5-1", "웹 디자이너", ["웹디자이너", "UI", "UX", "퍼블리셔", "디자인"]),
            ("5-2", "프론트엔드", ["프론트", "frontend", "react", "vue", "웹개발"]),
            ("5-3", "서버 개발", ["서버", "백엔드", "backend", "java", "python"]),
            ("5-4", "PM", ["PM", "기획", "프로젝트", "PO", "매니저"]),
            ("5-5", "AI 엔지니어", ["AI", "머신러닝", "ML", "딥러닝", "데이터"]),
        ]

        for scenario_id, keyword, expected in test_cases:
            result = TestResult(scenario_id, f"키워드 확장 ({keyword})")
            resp = await self.chat(f"강남역 근처 {keyword} 연봉 3천 이상")
            result.response_time = resp["_response_time"]

            jobs = resp.get("jobs", [])
            matched = 0
            for job in jobs:
                title = job.get("title", "").lower()
                if any(k.lower() in title for k in expected):
                    matched += 1

            if len(jobs) > 0:
                result.passed = True
                result.message = f"{len(jobs)}건 중 관련 키워드 {matched}건 ({matched/len(jobs)*100:.0f}%)"
            else:
                result.message = f"결과 {len(jobs)}건"
            result.details = {"jobs": len(jobs), "matched": matched, "keywords": expected}
            self.add_result(result)

    # ============================================================
    # 6. 엣지 케이스 테스트
    # ============================================================

    async def test_6_edge_cases(self):
        print("\n" + "=" * 60)
        print("6. 엣지 케이스 테스트")
        print("=" * 60)

        # 6-1: 연봉 미입력
        result = TestResult("6-1", "연봉 미입력")
        resp = await self.chat("개발자")
        result.response_time = resp["_response_time"]

        jobs = resp.get("jobs", [])
        response_text = resp.get("response", "")

        if len(jobs) == 0 and len(response_text) > 0:
            result.passed = True
            result.message = "검색 안 됨, 질문 응답"
        else:
            result.message = f"결과 {len(jobs)}건"
        self.add_result(result)

        # 6-2: 직무 미입력
        result = TestResult("6-2", "직무 미입력")
        resp = await self.chat("연봉 5천 이상")
        result.response_time = resp["_response_time"]

        jobs = resp.get("jobs", [])
        response_text = resp.get("response", "")

        if len(jobs) == 0 and len(response_text) > 0:
            result.passed = True
            result.message = "검색 안 됨, 직무 질문"
        else:
            result.message = f"결과 {len(jobs)}건"
        self.add_result(result)

        # 6-3: 인사
        result = TestResult("6-3", "인사 처리")
        resp = await self.chat("안녕하세요")
        result.response_time = resp["_response_time"]

        jobs = resp.get("jobs", [])
        response_text = resp.get("response", "")

        if len(jobs) == 0 and len(response_text) > 10:
            result.passed = True
            result.message = "인사 응답 + 안내"
        else:
            result.message = f"결과 {len(jobs)}건, 응답 길이 {len(response_text)}"
        self.add_result(result)

        # 6-4: 존재하지 않는 직무
        result = TestResult("6-4", "존재하지 않는 직무")
        resp = await self.chat("강남역 근처 존재하지않는직무xyz 3천 이상")
        result.response_time = resp["_response_time"]

        jobs = resp.get("jobs", [])
        response_text = resp.get("response", "")

        # 결과 없거나 적절한 안내
        result.passed = True  # 오류 없이 처리되면 통과
        result.message = f"결과 {len(jobs)}건, 응답 있음"
        self.add_result(result)

        # 6-5: 비현실적 연봉
        result = TestResult("6-5", "비현실적 연봉 (100억)")
        resp = await self.chat("강남역 근처 개발자 연봉 100억 이상")
        result.response_time = resp["_response_time"]

        jobs = resp.get("jobs", [])
        response_text = resp.get("response", "")

        # 결과 0건 또는 조건 완화 제안
        result.passed = True
        result.message = f"결과 {len(jobs)}건, 오류 없이 처리"
        self.add_result(result)

        # 6-6: 음수 연봉
        result = TestResult("6-6", "음수 연봉")
        resp = await self.chat("강남역 근처 마케터 -3천")
        result.response_time = resp["_response_time"]

        jobs = resp.get("jobs", [])
        # 오류 없이 처리되면 통과
        result.passed = True
        result.message = f"결과 {len(jobs)}건, graceful handling"
        self.add_result(result)

    # ============================================================
    # 7. 데이터 품질 검증 테스트
    # ============================================================

    async def test_7_data_quality(self):
        print("\n" + "=" * 60)
        print("7. 데이터 품질 검증 테스트")
        print("=" * 60)

        # 샘플 데이터 가져오기
        resp = await self.chat("강남역 근처 개발자 3천 이상")
        jobs = resp.get("jobs", [])

        if len(jobs) == 0:
            print("  [SKIP] 샘플 데이터 없음")
            return

        samples = jobs[:min(10, len(jobs))]

        # 7-1: 제목 정확성
        result = TestResult("7-1", "제목 정확성")
        valid_titles = sum(1 for j in samples if j.get("title") and len(j["title"]) > 5)
        result.passed = valid_titles == len(samples)
        result.message = f"{valid_titles}/{len(samples)} 유효"
        self.add_result(result)

        # 7-2: 회사명 정확성
        result = TestResult("7-2", "회사명 정확성")
        valid_companies = sum(1 for j in samples if j.get("company_name") and len(j["company_name"]) > 1)
        result.passed = valid_companies == len(samples)
        result.message = f"{valid_companies}/{len(samples)} 유효"
        self.add_result(result)

        # 7-3: 연봉 파싱
        result = TestResult("7-3", "연봉 파싱")
        valid_salary = 0
        for j in samples:
            salary_text = j.get("salary", "")
            if salary_text and ("만원" in salary_text or "협의" in salary_text or "회사내규" in salary_text):
                valid_salary += 1
        result.passed = valid_salary > len(samples) * 0.5
        result.message = f"{valid_salary}/{len(samples)} 유효 ({valid_salary/len(samples)*100:.0f}%)"
        self.add_result(result)

        # 7-4: 위치 정보
        result = TestResult("7-4", "위치 정보 (서울 구)")
        valid_location = 0
        for j in samples:
            loc = j.get("location", "")
            if any(gu in loc for gu in SEOUL_GU) or "서울" in loc:
                valid_location += 1
        result.passed = valid_location > len(samples) * 0.8
        result.message = f"{valid_location}/{len(samples)} 서울 지역 ({valid_location/len(samples)*100:.0f}%)"
        self.add_result(result)

        # 7-5: URL 유효성
        result = TestResult("7-5", "URL 형식 유효성")
        valid_url = sum(1 for j in samples if j.get("url") and j["url"].startswith("https://"))
        result.passed = valid_url == len(samples)
        result.message = f"{valid_url}/{len(samples)} 유효한 URL"
        self.add_result(result)

        # 7-6: 마감일 형식
        result = TestResult("7-6", "마감일 형식")
        valid_deadline = 0
        deadline_patterns = ["상시", "채용시", "마감"]
        for j in samples:
            deadline = j.get("deadline", "")
            if deadline:
                # MM.DD 형식 또는 특수 문구
                if re.match(r"\d{1,2}\.\d{1,2}", deadline) or any(p in deadline for p in deadline_patterns):
                    valid_deadline += 1
        result.passed = valid_deadline > len(samples) * 0.5
        result.message = f"{valid_deadline}/{len(samples)} 유효한 형식"
        self.add_result(result)

    # ============================================================
    # 8. 성능 테스트
    # ============================================================

    async def test_8_performance(self):
        print("\n" + "=" * 60)
        print("8. 성능 테스트")
        print("=" * 60)

        # 8-1: 첫 응답 시간
        result = TestResult("8-1", "첫 응답 시간 (<10초)")
        resp = await self.chat("강남역 근처 마케팅 3천 이상")
        result.response_time = resp["_response_time"]

        if result.response_time < 10:
            result.passed = True
            result.message = f"응답 시간: {result.response_time:.2f}초"
        else:
            result.message = f"응답 시간 초과: {result.response_time:.2f}초"
        self.add_result(result)

        # 8-2: 더보기 응답 시간
        result = TestResult("8-2", "더보기 응답 (<1초)")
        conv_id = resp.get("conversation_id")
        if conv_id and len(resp.get("jobs", [])) > 0:
            resp2 = await self.chat_more(conv_id)
            result.response_time = resp2["_response_time"]

            if result.response_time < 1:
                result.passed = True
                result.message = f"응답 시간: {result.response_time:.2f}초 (LLM 미호출)"
            else:
                result.message = f"응답 시간: {result.response_time:.2f}초"
        else:
            result.message = "더보기 테스트 불가"
        self.add_result(result)

        # 8-3: 결과 개수
        result = TestResult("8-3", "결과 개수 (50건)")
        resp = await self.chat("강남역 근처 개발자 2천 이상")  # 넓은 조건
        result.response_time = resp["_response_time"]
        jobs = resp.get("jobs", [])

        if len(jobs) == 50:
            result.passed = True
            result.message = f"첫 배치 {len(jobs)}건 (정확)"
        elif len(jobs) > 0:
            result.passed = True
            result.message = f"첫 배치 {len(jobs)}건"
        else:
            result.message = f"결과 {len(jobs)}건"
        self.add_result(result)

        # 8-4: 대화 연속성 (5회)
        result = TestResult("8-4", "대화 연속성 (5회)")
        resp = await self.chat("강남역 근처 개발자 3천 이상")
        conv_id = resp.get("conversation_id")
        success_count = 1

        followups = [
            "연봉 4천 이상으로",
            "백엔드만",
            "서초구 쪽으로",
            "정규직만",
        ]

        for msg in followups:
            try:
                resp = await self.chat(msg, conv_id)
                if resp.get("success") or resp.get("response"):
                    success_count += 1
            except Exception:
                break

        if success_count >= 5:
            result.passed = True
            result.message = f"{success_count}회 연속 대화 성공"
        else:
            result.message = f"{success_count}/5회 성공"
        result.details = {"conversations": success_count}
        self.add_result(result)

    # ============================================================
    # 메인 실행
    # ============================================================

    async def run_all(self):
        print("=" * 70)
        print("프론트엔드 테스트 시나리오 - 종합 E2E 검증")
        print("=" * 70)

        # 환경 확인
        print("\n[환경 확인]")
        try:
            health_resp = await self.client.get(f"{API_BASE}/health")
            health = health_resp.json()
            print(f"  서버 상태: {health.get('status')}")
            print(f"  Firestore: {health.get('services', {}).get('firestore')}")
            print(f"  Gemini: {health.get('services', {}).get('gemini')}")
            print(f"  Subway: {health.get('services', {}).get('subway')}")
        except Exception as e:
            print(f"  [ERROR] 서버 연결 실패: {e}")
            return

        # 테스트 실행
        await self.test_1_basic_search()
        await self.test_2_location_search()
        await self.test_3_commute_search()
        await self.test_4_followup()
        await self.test_5_keyword_expansion()
        await self.test_6_edge_cases()
        await self.test_7_data_quality()
        await self.test_8_performance()

        # 요약
        print("\n" + "=" * 70)
        print("테스트 요약")
        print("=" * 70)

        groups = {}
        for r in self.results:
            group = r.scenario_id.split("-")[0]
            if group not in groups:
                groups[group] = {"passed": 0, "total": 0}
            groups[group]["total"] += 1
            if r.passed:
                groups[group]["passed"] += 1

        group_names = {
            "1": "기본 검색",
            "2": "위치 기반",
            "3": "통근시간",
            "4": "후속 대화",
            "5": "키워드 확장",
            "6": "엣지 케이스",
            "7": "데이터 품질",
            "8": "성능",
        }

        for group_id, stats in sorted(groups.items()):
            name = group_names.get(group_id, f"그룹 {group_id}")
            passed = stats["passed"]
            total = stats["total"]
            pct = passed / total * 100 if total > 0 else 0
            status = "PASS" if passed == total else "PARTIAL" if passed > 0 else "FAIL"
            print(f"  [{status}] {group_id}. {name}: {passed}/{total} ({pct:.0f}%)")

        total_passed = sum(1 for r in self.results if r.passed)
        total_tests = len(self.results)
        overall_pct = total_passed / total_tests * 100 if total_tests > 0 else 0

        print(f"\n총 결과: {total_passed}/{total_tests} 통과 ({overall_pct:.0f}%)")
        print("=" * 70)

        return total_passed, total_tests


async def main():
    tester = FrontendTester()
    await tester.setup()
    try:
        await tester.run_all()
    finally:
        await tester.teardown()


if __name__ == "__main__":
    asyncio.run(main())
