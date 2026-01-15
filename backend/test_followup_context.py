#!/usr/bin/env python3
"""후속 대화 컨텍스트 유지 테스트"""

import asyncio
import httpx
import uuid
import json
from typing import Dict, List, Optional

BASE_URL = "http://localhost:8000"

# 테스트용 좌표 (강남역)
STATION_COORDS = {
    "강남역": {"latitude": 37.497916, "longitude": 127.027632, "address": "강남역"},
    "홍대입구역": {"latitude": 37.557192, "longitude": 126.925427, "address": "홍대입구역"},
}


class TestClient:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=60.0)
        self.conversation_id = str(uuid.uuid4())

    async def chat(self, message: str, user_location: str = "") -> Dict:
        payload = {"message": message, "conversation_id": self.conversation_id}
        if user_location and user_location in STATION_COORDS:
            payload["user_location"] = STATION_COORDS[user_location]

        response = await self.client.post(f"{BASE_URL}/chat", json=payload)
        return response.json()

    async def close(self):
        await self.client.aclose()


async def test_scenario(name: str, messages: List[Dict], expected_checks: List[Dict]):
    """단일 시나리오 테스트"""
    print(f"\n{'='*60}")
    print(f"테스트: {name}")
    print("="*60)

    client = TestClient()
    results = []

    try:
        for i, msg_info in enumerate(messages):
            message = msg_info["message"]
            user_loc = msg_info.get("user_location", "")

            print(f"\n[{i+1}] 사용자: {message}")
            if user_loc:
                print(f"    위치: {user_loc}")

            result = await client.chat(message, user_loc)
            results.append(result)

            # API 응답 파싱 - search_params 사용 (filter_results도 search_params로 통일됨)
            params = result.get("search_params") or {}
            jobs = result.get("jobs", [])
            pagination = result.get("pagination") or {}

            print(f"    → 응답: {result.get('response', '')[:100]}...")
            print(f"    → params: {params}")
            print(f"    → 결과: {pagination.get('total_count', len(jobs))}건")

            # 검증
            if i < len(expected_checks):
                check = expected_checks[i]

                # params 또는 filter_params 검증
                for key, expected_val in check.items():
                    if key == "min_jobs":
                        actual = pagination.get("total_count", len(jobs))
                        if actual < expected_val:
                            print(f"    ❌ 결과 수 부족: {actual} < {expected_val}")
                        else:
                            print(f"    ✓ 결과 수: {actual} >= {expected_val}")
                    elif key.startswith("has_"):
                        # has_salary_min: salary_min이 있어야 함
                        param_key = key.replace("has_", "")
                        if param_key in params and params[param_key] is not None:
                            print(f"    ✓ {param_key} 유지됨: {params[param_key]}")
                        else:
                            print(f"    ❌ {param_key} 유실됨 (expected: 값이 있어야 함)")
                    elif key in params:
                        actual = params.get(key)
                        if actual == expected_val:
                            print(f"    ✓ {key}: {actual}")
                        else:
                            print(f"    ❌ {key}: {actual} (expected: {expected_val})")
                    else:
                        print(f"    ? {key} not in params")

            await asyncio.sleep(1)  # API 호출 간격

    finally:
        await client.close()

    return results


async def main():
    print("\n" + "="*70)
    print("후속 대화 컨텍스트 유지 테스트")
    print("="*70)

    # 시나리오 1: 연봉 변경 (이전: salary_min, company_location 유실)
    await test_scenario(
        "시나리오 1: 연봉 조건 변경",
        messages=[
            {"message": "백엔드 개발자 3000만원 이상 강남역 부근 채용공고", "user_location": "강남역"},
            {"message": "연봉 5000만원 이상만 보여줘"},
        ],
        expected_checks=[
            {"salary_min": 3000, "has_company_location": True},
            {"salary_min": 5000, "has_company_location": True},  # company_location 유지 확인
        ]
    )

    # 시나리오 2: 위치 필터 추가
    await test_scenario(
        "시나리오 2: 위치 필터 추가",
        messages=[
            {"message": "프론트엔드 개발자 연봉 4000 이상", "user_location": "홍대입구역"},
            {"message": "서초구 쪽만 보여줘"},
        ],
        expected_checks=[
            {"salary_min": 4000},
            {"has_salary_min": True, "has_company_location": True},  # salary_min, company_location 유지
        ]
    )

    # 시나리오 3: 통근시간 필터
    await test_scenario(
        "시나리오 3: 통근시간 필터",
        messages=[
            {"message": "데이터 분석가 연봉 무관", "user_location": "강남역"},
            {"message": "통근 40분 이내만"},
        ],
        expected_checks=[
            {"salary_min": 0},
            {"commute_max_minutes": 40},
        ]
    )

    # 시나리오 4: 복합 조건 변경
    await test_scenario(
        "시나리오 4: 복합 조건 유지",
        messages=[
            {"message": "PM 5000만원 이상 판교 근처", "user_location": "강남역"},
            {"message": "연봉 7000 이상으로 바꿔줘"},
        ],
        expected_checks=[
            {"salary_min": 5000, "has_company_location": True},
            {"salary_min": 7000, "has_company_location": True},  # company_location=판교 유지
        ]
    )

    # 시나리오 5: 직무 변경 (새 검색)
    await test_scenario(
        "시나리오 5: 직무 변경 (새 검색)",
        messages=[
            {"message": "백엔드 개발자 4000만원 이상", "user_location": "강남역"},
            {"message": "프론트엔드로 바꿔서 다시 찾아줘 연봉 3000 이상"},
        ],
        expected_checks=[
            {"salary_min": 4000},
            {"salary_min": 3000},  # 새 검색이므로 이전 조건 무시
        ]
    )

    print("\n" + "="*70)
    print("테스트 완료")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
