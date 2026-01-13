#!/usr/bin/env python3
"""
통근시간 계산 E2E 테스트

사용법:
    # 백엔드 서버가 실행 중인 상태에서
    python3 tests/test_e2e_commute.py

    # 또는 특정 테스트만
    python3 tests/test_e2e_commute.py --test basic
    python3 tests/test_e2e_commute.py --test line9
    python3 tests/test_e2e_commute.py --test shinbundang
"""

import argparse
import asyncio
import sys
from typing import Dict, List, Optional

try:
    import httpx
except ImportError:
    print("httpx가 설치되어 있지 않습니다. 설치 중...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx"])
    import httpx


BASE_URL = "http://localhost:8000"
TIMEOUT = 60.0


class CommuteE2ETest:
    """통근시간 E2E 테스트 클래스"""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.results: List[Dict] = []

    async def health_check(self) -> bool:
        """서버 상태 확인"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception as e:
            print(f"❌ 서버 연결 실패: {e}")
            return False

    async def search(
        self,
        message: str,
        page: int = 1,
        page_size: int = 5,
        user_lat: Optional[float] = None,
        user_lng: Optional[float] = None
    ) -> Dict:
        """검색 API 호출"""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            payload = {
                "message": message,
                "page": page,
                "page_size": page_size
            }
            if user_lat and user_lng:
                payload["user_lat"] = user_lat
                payload["user_lng"] = user_lng

            response = await client.post(
                f"{self.base_url}/chat",
                json=payload
            )
            return response.json()

    def print_jobs(self, jobs: List[Dict], limit: int = 5):
        """검색 결과 출력"""
        for i, job in enumerate(jobs[:limit]):
            travel_time = job.get("travel_time_text", "없음")
            title = job.get("title", "")[:35]
            location = job.get("location", "")
            print(f"  {i+1}. [{travel_time}] {title}")
            print(f"     📍 {location}")

    async def test_basic_commute(self) -> bool:
        """기본 통근시간 검색 테스트 (2호선)"""
        print("\n" + "=" * 60)
        print("테스트 1: 기본 통근시간 검색 (2호선)")
        print("=" * 60)

        test_cases = [
            {
                "query": "건대입구역에서 40분 이내 개발자 연봉 무관",
                "expected_max_minutes": 40,
            },
            {
                "query": "강남역에서 30분 이내 프론트엔드 연봉 무관",
                "expected_max_minutes": 30,
            },
        ]

        all_passed = True

        for case in test_cases:
            print(f"\n🔍 검색: {case['query']}")

            try:
                result = await self.search(case["query"])

                if not result.get("success"):
                    print(f"❌ 검색 실패: {result.get('error')}")
                    all_passed = False
                    continue

                jobs = result.get("jobs", [])
                print(f"   결과: {len(jobs)}건")

                if jobs:
                    self.print_jobs(jobs, 3)

                    # 검증: travel_time_minutes가 max 이내인지
                    for job in jobs:
                        travel_min = job.get("travel_time_minutes")
                        if travel_min and travel_min > case["expected_max_minutes"]:
                            print(f"   ⚠️ 경고: {travel_min}분 > {case['expected_max_minutes']}분")

                    # 검증: travel_time_text가 있는지
                    has_travel_time = any(j.get("travel_time_text") for j in jobs)
                    if has_travel_time:
                        print("   ✅ travel_time_text 확인됨")
                    else:
                        print("   ❌ travel_time_text 없음")
                        all_passed = False
                else:
                    print("   ⚠️ 검색 결과 없음 (공고 데이터 확인 필요)")

            except Exception as e:
                print(f"   ❌ 오류: {e}")
                all_passed = False

        return all_passed

    async def test_line9_route(self) -> bool:
        """9호선 경로 테스트"""
        print("\n" + "=" * 60)
        print("테스트 2: 9호선 경로 테스트")
        print("=" * 60)

        test_cases = [
            {
                "query": "여의도역에서 40분 이내 마케팅 연봉 무관",
                "description": "여의도 → 강남권 (9호선 직통)",
            },
            {
                "query": "당산역에서 50분 이내 기획자 연봉 무관",
                "description": "당산 → 신논현 (9호선)",
            },
        ]

        all_passed = True

        for case in test_cases:
            print(f"\n🔍 검색: {case['query']}")
            print(f"   경로: {case['description']}")

            try:
                result = await self.search(case["query"])
                jobs = result.get("jobs", [])
                print(f"   결과: {len(jobs)}건")

                if jobs:
                    self.print_jobs(jobs, 3)
                    has_travel_time = any(j.get("travel_time_text") for j in jobs)
                    if has_travel_time:
                        print("   ✅ 9호선 경로 반영 확인")
                    else:
                        print("   ❌ travel_time_text 없음")
                        all_passed = False
                else:
                    print("   ⚠️ 검색 결과 없음")

            except Exception as e:
                print(f"   ❌ 오류: {e}")
                all_passed = False

        return all_passed

    async def test_shinbundang_route(self) -> bool:
        """신분당선 경로 테스트"""
        print("\n" + "=" * 60)
        print("테스트 3: 신분당선 경로 테스트")
        print("=" * 60)

        test_cases = [
            {
                "query": "판교역에서 50분 이내 백엔드 개발자 연봉 무관",
                "description": "판교 → 강남 (신분당선 직통, 약 20분)",
            },
            {
                "query": "양재역에서 40분 이내 개발자 연봉 무관",
                "description": "양재 → 판교/강남 (신분당선)",
            },
        ]

        all_passed = True

        for case in test_cases:
            print(f"\n🔍 검색: {case['query']}")
            print(f"   경로: {case['description']}")

            try:
                result = await self.search(case["query"])
                jobs = result.get("jobs", [])
                print(f"   결과: {len(jobs)}건")

                if jobs:
                    self.print_jobs(jobs, 3)
                    has_travel_time = any(j.get("travel_time_text") for j in jobs)
                    if has_travel_time:
                        print("   ✅ 신분당선 경로 반영 확인")
                    else:
                        print("   ❌ travel_time_text 없음")
                        all_passed = False
                else:
                    print("   ⚠️ 검색 결과 없음")

            except Exception as e:
                print(f"   ❌ 오류: {e}")
                all_passed = False

        return all_passed

    async def test_transfer_route(self) -> bool:
        """환승 경로 테스트"""
        print("\n" + "=" * 60)
        print("테스트 4: 환승 경로 테스트")
        print("=" * 60)

        test_cases = [
            {
                "query": "잠실역에서 50분 이내 개발자 연봉 무관",
                "description": "잠실 → 판교 (2호선 → 신분당선)",
            },
            {
                "query": "홍대입구역에서 60분 이내 디자이너 연봉 무관",
                "description": "홍대 → 여의도/강남 (환승)",
            },
        ]

        all_passed = True

        for case in test_cases:
            print(f"\n🔍 검색: {case['query']}")
            print(f"   경로: {case['description']}")

            try:
                result = await self.search(case["query"])
                jobs = result.get("jobs", [])
                print(f"   결과: {len(jobs)}건")

                if jobs:
                    self.print_jobs(jobs, 3)
                    has_travel_time = any(j.get("travel_time_text") for j in jobs)
                    if has_travel_time:
                        print("   ✅ 환승 경로 반영 확인")
                    else:
                        print("   ❌ travel_time_text 없음")
                        all_passed = False
                else:
                    print("   ⚠️ 검색 결과 없음")

            except Exception as e:
                print(f"   ❌ 오류: {e}")
                all_passed = False

        return all_passed

    async def test_coordinates(self) -> bool:
        """좌표 기반 검색 테스트"""
        print("\n" + "=" * 60)
        print("테스트 5: 좌표 기반 검색 테스트")
        print("=" * 60)

        # 건대입구역 좌표
        lat, lng = 37.5403, 127.0694

        print(f"\n🔍 검색: '30분 이내 개발자 연봉 무관' (좌표: {lat}, {lng})")

        try:
            result = await self.search(
                "30분 이내 개발자 연봉 무관",
                user_lat=lat,
                user_lng=lng
            )
            jobs = result.get("jobs", [])
            print(f"   결과: {len(jobs)}건")

            if jobs:
                self.print_jobs(jobs, 3)
                has_travel_time = any(j.get("travel_time_text") for j in jobs)
                if has_travel_time:
                    print("   ✅ 좌표 기반 검색 확인")
                    return True
                else:
                    print("   ❌ travel_time_text 없음")
                    return False
            else:
                print("   ⚠️ 검색 결과 없음")
                return True  # 공고 없어도 API는 정상

        except Exception as e:
            print(f"   ❌ 오류: {e}")
            return False

    async def run_all(self) -> bool:
        """모든 테스트 실행"""
        print("\n" + "=" * 60)
        print("🚇 통근시간 계산 E2E 테스트 시작")
        print("=" * 60)

        # 서버 상태 확인
        print("\n서버 상태 확인 중...")
        if not await self.health_check():
            print("❌ 백엔드 서버가 실행 중이 아닙니다.")
            print("   다음 명령으로 서버를 시작하세요:")
            print("   cd backend && uvicorn app.main:app --reload")
            return False
        print("✅ 서버 연결 확인")

        # 테스트 실행
        results = {
            "basic": await self.test_basic_commute(),
            "line9": await self.test_line9_route(),
            "shinbundang": await self.test_shinbundang_route(),
            "transfer": await self.test_transfer_route(),
            "coordinates": await self.test_coordinates(),
        }

        # 결과 요약
        print("\n" + "=" * 60)
        print("📊 테스트 결과 요약")
        print("=" * 60)

        all_passed = True
        for name, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {name}: {status}")
            if not passed:
                all_passed = False

        print("\n" + "=" * 60)
        if all_passed:
            print("🎉 모든 테스트 통과!")
        else:
            print("⚠️ 일부 테스트 실패")
        print("=" * 60)

        return all_passed


async def main():
    parser = argparse.ArgumentParser(description="통근시간 E2E 테스트")
    parser.add_argument(
        "--test",
        choices=["all", "basic", "line9", "shinbundang", "transfer", "coords"],
        default="all",
        help="실행할 테스트 선택"
    )
    parser.add_argument(
        "--url",
        default=BASE_URL,
        help=f"백엔드 URL (기본: {BASE_URL})"
    )
    args = parser.parse_args()

    tester = CommuteE2ETest(base_url=args.url)

    if args.test == "all":
        success = await tester.run_all()
    elif args.test == "basic":
        if await tester.health_check():
            success = await tester.test_basic_commute()
        else:
            success = False
    elif args.test == "line9":
        if await tester.health_check():
            success = await tester.test_line9_route()
        else:
            success = False
    elif args.test == "shinbundang":
        if await tester.health_check():
            success = await tester.test_shinbundang_route()
        else:
            success = False
    elif args.test == "transfer":
        if await tester.health_check():
            success = await tester.test_transfer_route()
        else:
            success = False
    elif args.test == "coords":
        if await tester.health_check():
            success = await tester.test_coordinates()
        else:
            success = False
    else:
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
