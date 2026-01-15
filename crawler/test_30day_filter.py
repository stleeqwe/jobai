#!/usr/bin/env python3
"""크롤러 테스트 스크립트"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# 경로 설정 (상대 경로)
sys.path.insert(0, str(Path(__file__).parent))

from app.scrapers.jobkorea import JobKoreaScraper


async def main():
    print("=" * 60)
    print("크롤러 테스트")
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    scraper = JobKoreaScraper(num_workers=1)

    try:
        # 테스트: 3페이지만 크롤링 (약 200건)
        job_count, job_ids, stats = await scraper.crawl_all_parallel(
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
        print(f"  - 수집된 공고: {job_count}건")
        print(f"  - 스킵: {summary['total_skipped']}건")
        print(f"  - 실패: {summary['total_failed']}건")
        print(f"  - 차단 감지: {'예' if summary['is_blocked'] else '아니오'}")
        print(f"  - 소요 시간: {summary['elapsed_seconds']}초 ({summary['elapsed_minutes']}분)")

        # 수집된 ID 샘플
        print(f"\n[수집된 ID 샘플 (최대 5개)]")
        sample_ids = list(job_ids)[:5]
        for job_id in sample_ids:
            print(f"  - {job_id}")

        print("\n" + "=" * 60)
        print("테스트 완료!")
        print("=" * 60)

    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
