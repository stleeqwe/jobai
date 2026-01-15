#!/usr/bin/env python3
"""V2 크롤러 - 500페이지 크롤링"""

import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.scrapers.jobkorea_v2 import JobKoreaScraperV2
from app.db.firestore import save_jobs, get_job_stats, save_crawl_log


async def run_crawl_500():
    """500페이지 크롤링"""
    start_time = datetime.now()

    print("=" * 70)
    print("V2 크롤링 (500페이지 제한)")
    print(f"시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # DB 상태
    stats_before = await get_job_stats()
    print(f"\n[DB] 현재: {stats_before['total_jobs']:,}건, 활성: {stats_before['active_jobs']:,}건")

    # 크롤러
    scraper = JobKoreaScraperV2(num_workers=10, use_proxy=False, fallback_to_proxy=True)

    try:
        await scraper.initialize()
        print(f"[INFO] 서울 전체: {scraper.total_count:,}건")
        print(f"[INFO] 500페이지 = ~20,000건 수집 예정")

        # 500페이지만 크롤링
        success, job_ids, save_stats = await scraper.crawl_all(
            max_pages=500,
            save_callback=save_jobs,
            save_batch_size=500,
        )

        end_time = datetime.now()
        elapsed = (end_time - start_time).total_seconds()

        # 결과
        print("\n" + "=" * 70)
        print("완료!")
        print(f"  - 수집 ID: {len(job_ids):,}개")
        print(f"  - 상세 성공: {success:,}건")
        print(f"  - 신규: {save_stats.get('new', 0):,}건")
        print(f"  - 업데이트: {save_stats.get('updated', 0):,}건")
        print(f"  - 소요: {elapsed/60:.1f}분")
        print(f"  - 속도: {success/elapsed:.1f}건/s")

        # DB 상태
        stats_after = await get_job_stats()
        print(f"\n[DB] 결과: {stats_after['total_jobs']:,}건 (+{stats_after['total_jobs'] - stats_before['total_jobs']:,})")

        # 로그 저장
        await save_crawl_log({
            "started_at": start_time.isoformat(),
            "finished_at": end_time.isoformat(),
            "elapsed_seconds": int(elapsed),
            "total_ids": len(job_ids),
            "success": success,
            "new": save_stats.get("new", 0),
            "updated": save_stats.get("updated", 0),
            "version": "v2",
            "max_pages": 500,
        })

    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(run_crawl_500())
