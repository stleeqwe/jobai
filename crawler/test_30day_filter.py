#!/usr/bin/env python3
"""30일 필터링 크롤러 테스트 스크립트"""

import asyncio
import sys
from datetime import datetime

# 경로 설정
sys.path.insert(0, "/Users/stlee/Desktop/jobbot/jobai/crawler")

from app.scrapers.jobkorea import JobKoreaScraper


async def main():
    print("=" * 60)
    print("30일 필터링 크롤러 테스트")
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    scraper = JobKoreaScraper(num_workers=1)

    try:
        # 테스트: 3페이지만 크롤링 (약 200건)
        jobs, stats = await scraper.crawl_all_parallel(
            max_pages=3,
            save_callback=None,  # 저장 없이 테스트
            save_batch_size=100
        )

        print("\n" + "=" * 60)
        print("테스트 결과")
        print("=" * 60)

        # 통계 출력
        summary = scraper.stats.summary()
        print(f"\n[통계]")
        print(f"  - 수집된 공고: {len(jobs)}건")
        print(f"  - 30일 이전 공고 스킵: {summary['old_jobs_skipped']}건")
        print(f"  - 30일 조기 중단: {'예' if summary['stopped_by_old_jobs'] else '아니오'}")
        print(f"  - 소요 시간: {summary['elapsed_seconds']}초")

        # posted_at 필드 확인
        print(f"\n[posted_at 필드 확인]")
        jobs_with_posted_at = [j for j in jobs if j.get("posted_at")]
        print(f"  - posted_at 있음: {len(jobs_with_posted_at)}건")
        print(f"  - posted_at 없음: {len(jobs) - len(jobs_with_posted_at)}건")

        # 샘플 출력
        if jobs_with_posted_at:
            print(f"\n[샘플 공고 (최신 5건)]")
            for job in jobs_with_posted_at[:5]:
                posted_at = job.get("posted_at")
                posted_str = posted_at.strftime("%Y-%m-%d") if posted_at else "N/A"
                print(f"  - [{posted_str}] {job.get('title', '')[:40]}...")
                print(f"    회사: {job.get('company_name', 'N/A')}")
                print(f"    지역: {job.get('location_sido', 'N/A')} {job.get('location_gugun', '')}")

        print("\n" + "=" * 60)
        print("테스트 완료!")
        print("=" * 60)

    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
