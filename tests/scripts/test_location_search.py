#!/usr/bin/env python3
"""
지역/위치 검색 검증 테스트 스크립트

서울시 구/동/역 단위 검색이 정상적으로 동작하는지 검증합니다.
복합 질의: 직무 + 연봉 + 지역 필수
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import httpx

API_BASE = "http://localhost:8000"

# 고정 파라미터
JOB_TYPE = "개발자"
SALARY = "3500만원"

# ============================================================
# 테스트 대상 지역
# ============================================================

SEOUL_DISTRICTS = [
    "강남구", "강동구", "강북구", "강서구", "관악구",
    "광진구", "구로구", "금천구", "노원구", "도봉구",
    "동대문구", "동작구", "마포구", "서대문구", "서초구",
    "성동구", "성북구", "송파구", "양천구", "영등포구",
    "용산구", "은평구", "종로구", "중구", "중랑구"
]

STATIONS = [
    # 강남권
    "강남역", "역삼역", "선릉역", "삼성역", "논현역", "신논현역", "압구정역",
    # 서초권
    "서초역", "교대역", "양재역",
    # 송파권
    "잠실역", "석촌역",
    # 강동권
    "천호역",
    # 광진권
    "건대입구역",
    # 마포권
    "홍대입구역", "합정역", "상수역", "망원역",
    # 영등포권
    "여의도역", "영등포구청역", "당산역",
    # 용산권
    "용산역", "이태원역",
    # 종로권
    "광화문역", "종각역", "안국역",
    # 중구권
    "을지로역", "명동역", "충무로역", "서울역",
    # 성동권
    "성수역", "뚝섬역", "왕십리역",
    # 구로/금천권
    "가산디지털단지역", "구로디지털단지역", "독산역", "신도림역",
]

DONGS = [
    "성수동", "여의도", "테헤란로", "삼성동", "역삼동",
    "논현동", "신사동", "청담동", "서초동", "반포동",
    "잠실동", "문정동", "가산동", "구로동", "홍대",
    "망원동", "합정동", "상암동", "이태원동"
]


class TestResult:
    def __init__(self, location: str, location_type: str):
        self.location = location
        self.location_type = location_type
        self.query = ""
        self.job_count = 0
        self.success = False
        self.error: Optional[str] = None
        self.sample_locations: List[str] = []
        self.response_time: float = 0


async def test_location(
    client: httpx.AsyncClient,
    location: str,
    location_type: str
) -> TestResult:
    """단일 지역 테스트"""
    result = TestResult(location, location_type)

    # 질의 생성
    if location_type == "station":
        result.query = f"{location} 근처 연봉 {SALARY} 이상 {JOB_TYPE} 공고 찾아줘"
    else:
        result.query = f"{location}에서 연봉 {SALARY} 이상 {JOB_TYPE} 채용 공고 찾아줘"

    try:
        start = datetime.now()
        resp = await client.post(
            f"{API_BASE}/chat",
            json={"message": result.query, "conversation_id": None}
        )
        result.response_time = (datetime.now() - start).total_seconds()

        data = resp.json()
        jobs = data.get("jobs", [])

        result.job_count = len(jobs)
        result.success = len(jobs) > 0
        result.sample_locations = [
            j.get("location", "")[:40] for j in jobs[:3]
        ]

    except Exception as e:
        result.error = str(e)

    return result


async def run_district_tests(client: httpx.AsyncClient) -> List[TestResult]:
    """구 단위 테스트"""
    print("\n" + "=" * 60)
    print("Phase 1: 구 단위 검색 테스트 (25개)")
    print("=" * 60)

    results = []
    for i, gu in enumerate(SEOUL_DISTRICTS, 1):
        result = await test_location(client, gu, "district")
        results.append(result)

        status = "✓" if result.success else "✗"
        print(f"  [{i:2d}/25] {gu:6s}: {result.job_count:3d}건 {status} ({result.response_time:.1f}s)")

        if result.error:
            print(f"         ERROR: {result.error}")

    return results


async def run_station_tests(client: httpx.AsyncClient) -> List[TestResult]:
    """역 단위 테스트"""
    print("\n" + "=" * 60)
    print(f"Phase 2: 역 단위 검색 테스트 ({len(STATIONS)}개)")
    print("=" * 60)

    results = []
    for i, station in enumerate(STATIONS, 1):
        result = await test_location(client, station, "station")
        results.append(result)

        status = "✓" if result.success else "✗"
        print(f"  [{i:2d}/{len(STATIONS)}] {station:12s}: {result.job_count:3d}건 {status} ({result.response_time:.1f}s)")

        if result.error:
            print(f"         ERROR: {result.error}")

    return results


async def run_dong_tests(client: httpx.AsyncClient) -> List[TestResult]:
    """동 단위 테스트"""
    print("\n" + "=" * 60)
    print(f"Phase 3: 동/지역 단위 검색 테스트 ({len(DONGS)}개)")
    print("=" * 60)

    results = []
    for i, dong in enumerate(DONGS, 1):
        result = await test_location(client, dong, "dong")
        results.append(result)

        status = "✓" if result.success else "✗"
        print(f"  [{i:2d}/{len(DONGS)}] {dong:8s}: {result.job_count:3d}건 {status} ({result.response_time:.1f}s)")

        if result.error:
            print(f"         ERROR: {result.error}")

    return results


def print_summary(
    district_results: List[TestResult],
    station_results: List[TestResult],
    dong_results: List[TestResult]
):
    """결과 요약 출력"""
    print("\n" + "=" * 70)
    print("테스트 결과 요약")
    print("=" * 70)

    # 구 단위
    district_success = sum(1 for r in district_results if r.success)
    district_total = len(district_results)
    district_rate = district_success / district_total * 100 if district_total else 0

    print(f"\n[구 단위] {district_success}/{district_total} 성공 ({district_rate:.0f}%)")
    failed_districts = [r.location for r in district_results if not r.success]
    if failed_districts:
        print(f"  실패: {', '.join(failed_districts)}")

    # 역 단위
    station_success = sum(1 for r in station_results if r.success)
    station_total = len(station_results)
    station_rate = station_success / station_total * 100 if station_total else 0

    print(f"\n[역 단위] {station_success}/{station_total} 성공 ({station_rate:.0f}%)")
    failed_stations = [r.location for r in station_results if not r.success]
    if failed_stations:
        print(f"  실패: {', '.join(failed_stations)}")

    # 동 단위
    dong_success = sum(1 for r in dong_results if r.success)
    dong_total = len(dong_results)
    dong_rate = dong_success / dong_total * 100 if dong_total else 0

    print(f"\n[동 단위] {dong_success}/{dong_total} 성공 ({dong_rate:.0f}%)")
    failed_dongs = [r.location for r in dong_results if not r.success]
    if failed_dongs:
        print(f"  실패: {', '.join(failed_dongs)}")

    # 전체
    total_success = district_success + station_success + dong_success
    total_tests = district_total + station_total + dong_total
    total_rate = total_success / total_tests * 100 if total_tests else 0

    print("\n" + "-" * 70)
    print(f"전체: {total_success}/{total_tests} 성공 ({total_rate:.0f}%)")

    # 합격 기준 판정
    print("\n" + "=" * 70)
    print("합격 기준 판정")
    print("=" * 70)

    criteria = [
        ("구 단위 80% 이상", district_rate >= 80, f"{district_rate:.0f}%"),
        ("역 단위 90% 이상", station_rate >= 90, f"{station_rate:.0f}%"),
        ("동 단위 80% 이상", dong_rate >= 80, f"{dong_rate:.0f}%"),
    ]

    all_pass = True
    for name, passed, value in criteria:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}: {value}")
        if not passed:
            all_pass = False

    print("\n" + "-" * 70)
    if all_pass:
        print("최종 결과: PASS - 모든 기준 충족")
    else:
        print("최종 결과: FAIL - 일부 기준 미달")
    print("=" * 70)

    return {
        "district": {"success": district_success, "total": district_total, "rate": district_rate},
        "station": {"success": station_success, "total": station_total, "rate": station_rate},
        "dong": {"success": dong_success, "total": dong_total, "rate": dong_rate},
        "total": {"success": total_success, "total": total_tests, "rate": total_rate},
        "all_pass": all_pass,
        "failed": {
            "districts": failed_districts,
            "stations": failed_stations,
            "dongs": failed_dongs
        }
    }


async def check_server() -> bool:
    """서버 상태 확인"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{API_BASE}/health")
            data = resp.json()
            status = data.get("status", "unknown")
            print(f"서버 상태: {status}")
            # "ok" 또는 "healthy" 모두 허용
            return status in ("ok", "healthy")
        except Exception as e:
            print(f"서버 연결 실패: {e}")
            return False


async def main():
    """메인 실행"""
    print("=" * 70)
    print("지역/위치 검색 검증 테스트")
    print(f"테스트 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"테스트 조건: 직무={JOB_TYPE}, 연봉={SALARY}")
    print("=" * 70)

    # 서버 상태 확인
    if not await check_server():
        print("\n[ERROR] 백엔드 서버가 실행되지 않았습니다.")
        print("다음 명령으로 서버를 시작하세요:")
        print("  cd backend && source venv/bin/activate && uvicorn app.main:app --port 8000")
        return

    # 테스트 실행
    async with httpx.AsyncClient(timeout=60.0) as client:
        district_results = await run_district_tests(client)
        station_results = await run_station_tests(client)
        dong_results = await run_dong_tests(client)

    # 결과 요약
    summary = print_summary(district_results, station_results, dong_results)

    # JSON 결과 저장
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(output_dir, "location_search_results.json")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "config": {"job_type": JOB_TYPE, "salary": SALARY},
            "summary": summary,
            "details": {
                "districts": [
                    {
                        "location": r.location,
                        "job_count": r.job_count,
                        "success": r.success,
                        "response_time": r.response_time,
                        "sample_locations": r.sample_locations
                    }
                    for r in district_results
                ],
                "stations": [
                    {
                        "location": r.location,
                        "job_count": r.job_count,
                        "success": r.success,
                        "response_time": r.response_time,
                        "sample_locations": r.sample_locations
                    }
                    for r in station_results
                ],
                "dongs": [
                    {
                        "location": r.location,
                        "job_count": r.job_count,
                        "success": r.success,
                        "response_time": r.response_time,
                        "sample_locations": r.sample_locations
                    }
                    for r in dong_results
                ]
            }
        }, f, ensure_ascii=False, indent=2)

    print(f"\n결과 저장: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
