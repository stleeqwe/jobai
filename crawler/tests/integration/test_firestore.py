#!/usr/bin/env python3
"""
V2 크롤러 + Firestore 저장 테스트
- 100건만 수집해서 실제 DB 저장 확인
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.scrapers.jobkorea_v2 import JobKoreaScraperV2
from app.db.firestore import save_jobs, get_job_stats


async def test_db_save():
    """실제 DB 저장 테스트 (100건)"""
    print("=" * 60)
    print("V2 크롤러 + Firestore 저장 테스트")
    print("=" * 60)

    # 현재 DB 상태 확인
    print("\n[1] 현재 DB 상태 확인...")
    try:
        stats_before = await get_job_stats()
        print(f"  - 전체 공고: {stats_before['total_jobs']}건")
        print(f"  - 활성 공고: {stats_before['active_jobs']}건")
    except Exception as e:
        print(f"  - DB 연결 실패: {e}")
        return

    # V2 크롤러 초기화
    print("\n[2] V2 크롤러 초기화...")
    scraper = JobKoreaScraperV2(num_workers=5)

    try:
        await scraper.initialize()
        print(f"  - 서울 전체 공고: {scraper.total_count:,}건")

        # 3페이지만 수집 (~120건)
        print("\n[3] 목록 수집 (3페이지)...")
        job_ids = await scraper.crawl_list(max_pages=3)
        print(f"  - 수집된 ID: {len(job_ids)}개")

        # 상세 수집 + DB 저장
        print("\n[4] 상세 수집 + DB 저장...")
        success, save_stats = await scraper.crawl_details(
            job_ids,
            save_callback=save_jobs,
            batch_size=50,
            parallel_batch=5,
        )

        print(f"\n[5] 저장 결과:")
        print(f"  - 상세 수집 성공: {success}건")
        print(f"  - 신규 저장: {save_stats.get('new', 0)}건")
        print(f"  - 업데이트: {save_stats.get('updated', 0)}건")
        print(f"  - 실패: {save_stats.get('failed', 0)}건")

        # 저장 후 DB 상태 확인
        print("\n[6] 저장 후 DB 상태...")
        stats_after = await get_job_stats()
        print(f"  - 전체 공고: {stats_after['total_jobs']}건 (+{stats_after['total_jobs'] - stats_before['total_jobs']})")
        print(f"  - 활성 공고: {stats_after['active_jobs']}건")

        print("\n" + "=" * 60)
        print("테스트 완료!")
        print("=" * 60)

    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(test_db_save())
