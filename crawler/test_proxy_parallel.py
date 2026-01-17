#!/usr/bin/env python3
"""
IPRoyal 프록시 병렬 테스트
- 다중 프록시 연결로 상세 페이지 속도 향상 가능성 확인
"""

import asyncio
import time
import random
from typing import List, Dict
import httpx

from app.core.proxy_env import get_proxy_url

BASE_URL = "https://www.jobkorea.co.kr"
DETAIL_URL = f"{BASE_URL}/Recruit/GI_Read"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0",
]

# 테스트용 Job ID (실제 존재하는 것들)
TEST_JOB_IDS = [
    "48419125", "48419124", "48419123", "48419122", "48419121",
    "48419120", "48419119", "48419118", "48419117", "48419116",
    "48419115", "48419114", "48419113", "48419112", "48419111",
    "48419110", "48419109", "48419108", "48419107", "48419106",
]

async def fetch_detail_page(
    client: httpx.AsyncClient,
    job_id: str
) -> Dict:
    """상세 페이지 가져오기"""
    start = time.time()
    try:
        resp = await client.get(f"{DETAIL_URL}/{job_id}")
        elapsed = time.time() - start
        return {
            "job_id": job_id,
            "status": resp.status_code,
            "size": len(resp.text),
            "time": elapsed,
            "success": resp.status_code == 200
        }
    except Exception as e:
        return {
            "job_id": job_id,
            "status": 0,
            "size": 0,
            "time": time.time() - start,
            "success": False,
            "error": str(e)
        }


async def test_single_client(num_requests: int = 10):
    """단일 프록시 클라이언트 테스트"""
    print("\n1. 단일 프록시 클라이언트 테스트")
    print("-" * 50)

    proxy_url = get_proxy_url()

    async with httpx.AsyncClient(
        timeout=30.0,
        headers={"User-Agent": USER_AGENTS[0]},
        proxy=proxy_url,
        follow_redirects=True,
    ) as client:

        start = time.time()
        results = []

        for job_id in TEST_JOB_IDS[:num_requests]:
            result = await fetch_detail_page(client, job_id)
            results.append(result)
            print(f"   {job_id}: {result['status']}, {result['time']*1000:.0f}ms")

        total_time = time.time() - start
        success = sum(1 for r in results if r['success'])

        print(f"\n   총 시간: {total_time:.2f}s")
        print(f"   성공: {success}/{num_requests}")
        print(f"   평균: {total_time/num_requests*1000:.0f}ms/건")
        print(f"   초당: {num_requests/total_time:.1f}건/s")

        return total_time, success


async def test_parallel_same_proxy(num_workers: int = 5, num_requests: int = 10):
    """동일 프록시로 병렬 요청 테스트"""
    print(f"\n2. 동일 프록시 {num_workers}개 병렬 테스트")
    print("-" * 50)

    proxy_url = get_proxy_url()
    job_ids = TEST_JOB_IDS[:num_requests]

    async def worker(worker_id: int, ids: List[str]) -> List[Dict]:
        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": USER_AGENTS[worker_id % len(USER_AGENTS)]},
            proxy=proxy_url,
            follow_redirects=True,
        ) as client:
            results = []
            for job_id in ids:
                result = await fetch_detail_page(client, job_id)
                results.append(result)
            return results

    # 작업 분배
    chunks = [job_ids[i::num_workers] for i in range(num_workers)]

    start = time.time()
    all_results = await asyncio.gather(
        *[worker(i, chunks[i]) for i in range(num_workers)]
    )
    total_time = time.time() - start

    flat_results = [r for chunk in all_results for r in chunk]
    success = sum(1 for r in flat_results if r['success'])

    print(f"   총 시간: {total_time:.2f}s")
    print(f"   성공: {success}/{num_requests}")
    print(f"   평균: {total_time/num_requests*1000:.0f}ms/건")
    print(f"   초당: {num_requests/total_time:.1f}건/s")

    return total_time, success


async def test_parallel_different_sessions(num_workers: int = 5, num_requests: int = 10):
    """다른 세션(IP)으로 병렬 요청 테스트"""
    print(f"\n3. 다른 세션(IP) {num_workers}개 병렬 테스트")
    print("-" * 50)

    job_ids = TEST_JOB_IDS[:num_requests]

    async def worker(worker_id: int, ids: List[str]) -> List[Dict]:
        # 각 워커마다 다른 세션 ID → 다른 IP
        session_id = f"w{worker_id:02d}{random.randint(0, 99999):05d}"
        proxy_url = get_proxy_url(session_id=session_id, lifetime="10m")

        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": USER_AGENTS[worker_id % len(USER_AGENTS)]},
            proxy=proxy_url,
            follow_redirects=True,
        ) as client:
            results = []
            for job_id in ids:
                result = await fetch_detail_page(client, job_id)
                results.append(result)
            return results

    chunks = [job_ids[i::num_workers] for i in range(num_workers)]

    start = time.time()
    all_results = await asyncio.gather(
        *[worker(i, chunks[i]) for i in range(num_workers)]
    )
    total_time = time.time() - start

    flat_results = [r for chunk in all_results for r in chunk]
    success = sum(1 for r in flat_results if r['success'])

    print(f"   총 시간: {total_time:.2f}s")
    print(f"   성공: {success}/{num_requests}")
    print(f"   평균: {total_time/num_requests*1000:.0f}ms/건")
    print(f"   초당: {num_requests/total_time:.1f}건/s")

    return total_time, success


async def test_no_proxy_parallel(num_workers: int = 5, num_requests: int = 10):
    """프록시 없이 병렬 요청 테스트 (비교용)"""
    print(f"\n4. 프록시 없이 {num_workers}개 병렬 테스트")
    print("-" * 50)

    job_ids = TEST_JOB_IDS[:num_requests]

    async def worker(worker_id: int, ids: List[str]) -> List[Dict]:
        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": USER_AGENTS[worker_id % len(USER_AGENTS)]},
            follow_redirects=True,
        ) as client:
            results = []
            for job_id in ids:
                result = await fetch_detail_page(client, job_id)
                results.append(result)
            return results

    chunks = [job_ids[i::num_workers] for i in range(num_workers)]

    start = time.time()
    all_results = await asyncio.gather(
        *[worker(i, chunks[i]) for i in range(num_workers)]
    )
    total_time = time.time() - start

    flat_results = [r for chunk in all_results for r in chunk]
    success = sum(1 for r in flat_results if r['success'])

    print(f"   총 시간: {total_time:.2f}s")
    print(f"   성공: {success}/{num_requests}")
    print(f"   평균: {total_time/num_requests*1000:.0f}ms/건")
    print(f"   초당: {num_requests/total_time:.1f}건/s")

    return total_time, success


async def main():
    print("=" * 60)
    print("IPRoyal 프록시 병렬 테스트")
    print("=" * 60)

    num_requests = 20
    num_workers = 5

    results = {}

    # 1. 단일 프록시 (순차)
    t1, s1 = await test_single_client(num_requests)
    results["단일 프록시 순차"] = {"time": t1, "success": s1, "rps": num_requests/t1}

    await asyncio.sleep(2)

    # 2. 동일 프록시 병렬
    t2, s2 = await test_parallel_same_proxy(num_workers, num_requests)
    results["동일 프록시 병렬"] = {"time": t2, "success": s2, "rps": num_requests/t2}

    await asyncio.sleep(2)

    # 3. 다른 세션(IP) 병렬
    t3, s3 = await test_parallel_different_sessions(num_workers, num_requests)
    results["다른 IP 병렬"] = {"time": t3, "success": s3, "rps": num_requests/t3}

    await asyncio.sleep(2)

    # 4. 프록시 없이 병렬
    t4, s4 = await test_no_proxy_parallel(num_workers, num_requests)
    results["프록시 없음 병렬"] = {"time": t4, "success": s4, "rps": num_requests/t4}

    # 결론
    print("\n" + "=" * 60)
    print("결과 비교")
    print("=" * 60)

    print(f"\n{'방식':<20} {'시간':>8} {'성공':>6} {'초당 처리':>10}")
    print("-" * 50)
    for name, data in results.items():
        print(f"{name:<20} {data['time']:>7.2f}s {data['success']:>5} {data['rps']:>9.1f}/s")

    # 30워커 예상
    print("\n" + "=" * 60)
    print("30워커 예상 (63,370건 기준)")
    print("=" * 60)

    fastest = min(results.values(), key=lambda x: x['time'])
    fastest_rps = fastest['rps']

    # 30워커로 스케일링 (선형 가정 × 0.7 효율)
    scaled_rps = fastest_rps * (30 / num_workers) * 0.7
    estimated_time = 63370 / scaled_rps

    print(f"   현재 최고 속도: {fastest_rps:.1f}건/s ({num_workers}워커)")
    print(f"   30워커 예상: {scaled_rps:.1f}건/s")
    print(f"   63,370건 예상 시간: {estimated_time:.0f}초 ({estimated_time/60:.1f}분)")


if __name__ == "__main__":
    asyncio.run(main())
