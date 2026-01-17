#!/usr/bin/env python3
"""
직무별 지역 검색 E2E 테스트

다양한 직무(마케터, 디자이너, 기획자, 영업 등)로
구/동/역 단위 지역 검색이 정상 동작하는지 검증합니다.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

import httpx

API_BASE = "http://localhost:8000"

# ============================================================
# 테스트 대상 직무
# ============================================================

JOB_TYPES = [
    {"name": "마케터", "keywords": ["마케팅", "마케터", "marketing", "광고", "홍보"]},
    {"name": "디자이너", "keywords": ["디자인", "디자이너", "design", "UI", "UX", "그래픽"]},
    {"name": "기획자", "keywords": ["기획", "PM", "PO", "프로덕트", "서비스기획"]},
    {"name": "영업", "keywords": ["영업", "세일즈", "sales", "영업관리", "B2B"]},
    {"name": "인사/HR", "keywords": ["인사", "HR", "채용", "HRD", "인재"]},
    {"name": "경영지원", "keywords": ["경영", "총무", "행정", "사무", "관리"]},
]

# 테스트 대상 지역 (샘플링 - 빠른 테스트용)
TEST_DISTRICTS = ["강남구", "마포구", "영등포구", "성동구"]
TEST_STATIONS = ["강남역", "홍대입구역", "성수역"]
TEST_DONGS = ["테헤란로", "홍대"]

# 연봉 조건 (직무별 현실적인 조건)
SALARY = "3000만원"


class TestResult:
    def __init__(self, job_type: str, location: str, location_type: str):
        self.job_type = job_type
        self.location = location
        self.location_type = location_type
        self.query = ""
        self.job_count = 0
        self.success = False
        self.error: Optional[str] = None
        self.response_time: float = 0
        self.keyword_match_count: int = 0


async def test_single(
    client: httpx.AsyncClient,
    job_type: Dict,
    location: str,
    location_type: str
) -> TestResult:
    """단일 직무+지역 테스트"""
    result = TestResult(job_type["name"], location, location_type)

    # 질의 생성
    if location_type == "station":
        result.query = f"{location} 근처 연봉 {SALARY} 이상 {job_type['name']} 공고 찾아줘"
    else:
        result.query = f"{location}에서 연봉 {SALARY} 이상 {job_type['name']} 채용 공고 찾아줘"

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

        # 키워드 매칭 확인
        keywords = job_type["keywords"]
        for job in jobs:
            title = job.get("title", "").lower()
            if any(k.lower() in title for k in keywords):
                result.keyword_match_count += 1

    except Exception as e:
        result.error = str(e)

    return result


async def run_job_type_tests(client: httpx.AsyncClient, job_type: Dict) -> Dict:
    """특정 직무에 대한 지역 테스트"""
    print(f"\n{'='*60}", flush=True)
    print(f"직무: {job_type['name']}", flush=True)
    print(f"키워드: {', '.join(job_type['keywords'][:3])}", flush=True)
    print("="*60)

    results = {
        "job_type": job_type["name"],
        "districts": [],
        "stations": [],
        "dongs": []
    }

    # 구 단위 테스트
    print(f"\n[구 단위] ({len(TEST_DISTRICTS)}개)")
    for gu in TEST_DISTRICTS:
        result = await test_single(client, job_type, gu, "district")
        results["districts"].append({
            "location": gu,
            "job_count": result.job_count,
            "success": result.success,
            "keyword_match": result.keyword_match_count,
            "response_time": result.response_time
        })
        status = "✓" if result.success else "✗"
        match_info = f"(매칭:{result.keyword_match_count})" if result.job_count > 0 else ""
        print(f"  {gu:8s}: {result.job_count:3d}건 {status} {match_info}")

    # 역 단위 테스트
    print(f"\n[역 단위] ({len(TEST_STATIONS)}개)")
    for station in TEST_STATIONS:
        result = await test_single(client, job_type, station, "station")
        results["stations"].append({
            "location": station,
            "job_count": result.job_count,
            "success": result.success,
            "keyword_match": result.keyword_match_count,
            "response_time": result.response_time
        })
        status = "✓" if result.success else "✗"
        match_info = f"(매칭:{result.keyword_match_count})" if result.job_count > 0 else ""
        print(f"  {station:12s}: {result.job_count:3d}건 {status} {match_info}")

    # 동 단위 테스트
    print(f"\n[동 단위] ({len(TEST_DONGS)}개)")
    for dong in TEST_DONGS:
        result = await test_single(client, job_type, dong, "dong")
        results["dongs"].append({
            "location": dong,
            "job_count": result.job_count,
            "success": result.success,
            "keyword_match": result.keyword_match_count,
            "response_time": result.response_time
        })
        status = "✓" if result.success else "✗"
        match_info = f"(매칭:{result.keyword_match_count})" if result.job_count > 0 else ""
        print(f"  {dong:8s}: {result.job_count:3d}건 {status} {match_info}")

    # 직무별 통계
    district_success = sum(1 for r in results["districts"] if r["success"])
    station_success = sum(1 for r in results["stations"] if r["success"])
    dong_success = sum(1 for r in results["dongs"] if r["success"])

    total_success = district_success + station_success + dong_success
    total_tests = len(TEST_DISTRICTS) + len(TEST_STATIONS) + len(TEST_DONGS)

    results["summary"] = {
        "district": f"{district_success}/{len(TEST_DISTRICTS)}",
        "station": f"{station_success}/{len(TEST_STATIONS)}",
        "dong": f"{dong_success}/{len(TEST_DONGS)}",
        "total": f"{total_success}/{total_tests}",
        "rate": total_success / total_tests * 100 if total_tests > 0 else 0
    }

    print(f"\n소계: {total_success}/{total_tests} 성공 ({results['summary']['rate']:.0f}%)")

    return results


def print_final_summary(all_results: List[Dict]):
    """최종 결과 요약"""
    print("\n" + "="*70)
    print("최종 결과 요약")
    print("="*70)

    print(f"\n{'직무':<12} {'구':<10} {'역':<10} {'동':<10} {'전체':<12} {'성공률':<8}")
    print("-"*70)

    total_success = 0
    total_tests = 0

    for result in all_results:
        job = result["job_type"]
        summary = result["summary"]

        d_parts = summary["district"].split("/")
        s_parts = summary["station"].split("/")
        g_parts = summary["dong"].split("/")
        t_parts = summary["total"].split("/")

        success = int(t_parts[0])
        tests = int(t_parts[1])
        rate = summary["rate"]

        total_success += success
        total_tests += tests

        status = "PASS" if rate >= 70 else "WARN" if rate >= 50 else "FAIL"
        print(f"{job:<12} {summary['district']:<10} {summary['station']:<10} {summary['dong']:<10} {summary['total']:<12} {rate:.0f}% [{status}]")

    overall_rate = total_success / total_tests * 100 if total_tests > 0 else 0

    print("-"*70)
    print(f"{'전체':<12} {'':<10} {'':<10} {'':<10} {total_success}/{total_tests:<6} {overall_rate:.0f}%")

    print("\n" + "="*70)
    print("합격 기준 판정 (직무별 70% 이상)")
    print("="*70)

    all_pass = True
    for result in all_results:
        job = result["job_type"]
        rate = result["summary"]["rate"]
        status = "PASS" if rate >= 70 else "FAIL"
        if rate < 70:
            all_pass = False
        print(f"  [{status}] {job}: {rate:.0f}%")

    print("\n" + "-"*70)
    if all_pass:
        print("최종 결과: PASS - 모든 직무에서 70% 이상 성공")
    else:
        failed = [r["job_type"] for r in all_results if r["summary"]["rate"] < 70]
        print(f"최종 결과: FAIL - {', '.join(failed)} 기준 미달")
    print("="*70)

    return all_pass


async def check_server() -> bool:
    """서버 상태 확인"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{API_BASE}/health")
            data = resp.json()
            status = data.get("status", "unknown")
            print(f"서버 상태: {status}")
            return status in ("ok", "healthy")
        except Exception as e:
            print(f"서버 연결 실패: {e}")
            return False


async def main():
    """메인 실행"""
    print("="*70)
    print("직무별 지역 검색 E2E 테스트")
    print(f"테스트 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"테스트 직무: {len(JOB_TYPES)}개")
    print(f"테스트 지역: 구 {len(TEST_DISTRICTS)}개, 역 {len(TEST_STATIONS)}개, 동 {len(TEST_DONGS)}개")
    print(f"연봉 조건: {SALARY}")
    print("="*70)

    # 서버 상태 확인
    if not await check_server():
        print("\n[ERROR] 백엔드 서버가 실행되지 않았습니다.")
        return

    all_results = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        for job_type in JOB_TYPES:
            result = await run_job_type_tests(client, job_type)
            all_results.append(result)

    # 최종 요약
    all_pass = print_final_summary(all_results)

    # JSON 결과 저장
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(output_dir, "job_type_location_results.json")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "config": {
                "salary": SALARY,
                "districts": TEST_DISTRICTS,
                "stations": TEST_STATIONS,
                "dongs": TEST_DONGS
            },
            "all_pass": all_pass,
            "results": all_results
        }, f, ensure_ascii=False, indent=2)

    print(f"\n결과 저장: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
