#!/usr/bin/env python3
"""
V2 크롤러 통합 테스트
- 목록 수집 + 상세 수집 1,000건 테스트
"""

import asyncio
import sys
import os

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.scrapers.jobkorea_v2 import JobKoreaScraperV2


async def test_list_only(pages: int = 25):
    """목록만 수집 테스트 (25페이지 = 1,000건)"""
    print("=" * 60)
    print(f"V2 목록 수집 테스트 ({pages}페이지)")
    print("=" * 60)

    scraper = JobKoreaScraperV2(num_workers=5)

    try:
        await scraper.initialize()

        job_ids = await scraper.crawl_list(max_pages=pages)

        print(f"\n결과:")
        print(f"  - 수집된 ID: {len(job_ids)}개")
        print(f"  - 예상: {pages * 40}개")
        print(f"  - 고유율: {len(job_ids) / (pages * 40) * 100:.1f}%")

        # 샘플 출력
        sample = list(job_ids)[:10]
        print(f"\n샘플 ID: {sample}")

        return job_ids

    finally:
        await scraper.close()


async def test_full_1000():
    """1,000건 전체 테스트 (목록 + 상세)"""
    print("=" * 60)
    print("V2 전체 테스트 (1,000건)")
    print("=" * 60)

    scraper = JobKoreaScraperV2(
        num_workers=5,
        use_proxy=False,
        fallback_to_proxy=True,
    )

    collected_jobs = []

    async def mock_save(jobs):
        """테스트용 저장 콜백 (실제 저장 안함)"""
        collected_jobs.extend(jobs)
        return {"new": len(jobs), "updated": 0}

    try:
        await scraper.initialize()

        # 25페이지 = ~1,000건
        success, job_ids, save_stats = await scraper.crawl_all(
            max_pages=25,
            save_callback=mock_save,
            save_batch_size=100,
        )

        print(f"\n최종 결과:")
        print(f"  - 목록 ID: {len(job_ids)}개")
        print(f"  - 상세 성공: {success}개")
        print(f"  - 저장 통계: {save_stats}")
        print(f"  - 프록시 전환: {'Yes' if scraper.stats.proxy_switched else 'No'}")

        # 샘플 데이터 출력
        if collected_jobs:
            sample = collected_jobs[0]
            print(f"\n샘플 데이터:")
            for k in ["id", "title", "company_name", "job_type", "salary_text", "location_sido"]:
                print(f"  - {k}: {sample.get(k, 'N/A')}")

        return collected_jobs

    finally:
        await scraper.close()


async def test_detail_speed():
    """상세 페이지 속도 테스트"""
    print("=" * 60)
    print("V2 상세 페이지 속도 테스트")
    print("=" * 60)

    scraper = JobKoreaScraperV2(num_workers=10)

    try:
        await scraper.initialize()

        # 5페이지 목록 수집 (~200건)
        job_ids = await scraper.crawl_list(max_pages=5)
        print(f"\n목록 수집 완료: {len(job_ids)}개")

        # 상세 수집
        import time
        start = time.time()

        success, _ = await scraper.crawl_details(
            job_ids,
            parallel_batch=10,
        )

        elapsed = time.time() - start
        speed = success / elapsed if elapsed > 0 else 0

        print(f"\n상세 수집 결과:")
        print(f"  - 성공: {success}개")
        print(f"  - 소요: {elapsed:.1f}초")
        print(f"  - 속도: {speed:.1f}건/s")
        print(f"  - 63,370건 예상: {63370 / speed / 60:.1f}분")

    finally:
        await scraper.close()


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="V2 크롤러 테스트")
    parser.add_argument("--mode", choices=["list", "full", "speed"], default="list")
    parser.add_argument("--pages", type=int, default=25)

    args = parser.parse_args()

    if args.mode == "list":
        await test_list_only(args.pages)
    elif args.mode == "full":
        await test_full_1000()
    elif args.mode == "speed":
        await test_detail_speed()


if __name__ == "__main__":
    asyncio.run(main())
