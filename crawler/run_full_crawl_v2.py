#!/usr/bin/env python3
"""
V2 크롤러 전체 크롤링 실행
- 63,370건 서울 전체 공고 수집
- 실시간 모니터링
"""

import asyncio
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.scrapers.jobkorea_v2 import JobKoreaScraperV2
from app.db.firestore import save_jobs, get_job_stats, save_crawl_log


async def run_full_crawl():
    """전체 크롤링 실행"""
    start_time = datetime.now()

    print("=" * 70)
    print("V2 전체 크롤링 시작")
    print(f"시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 현재 DB 상태
    print("\n[1] 현재 DB 상태...")
    try:
        stats_before = await get_job_stats()
        print(f"  - 전체 공고: {stats_before['total_jobs']:,}건")
        print(f"  - 활성 공고: {stats_before['active_jobs']:,}건")
    except Exception as e:
        print(f"  - DB 조회 실패: {e}")
        stats_before = {"total_jobs": 0, "active_jobs": 0}

    # V2 크롤러 초기화
    print("\n[2] V2 크롤러 초기화...")
    scraper = JobKoreaScraperV2(
        num_workers=10,
        use_proxy=False,
        fallback_to_proxy=True,
    )

    try:
        await scraper.initialize()
        total_count = scraper.total_count
        total_pages = scraper.total_pages

        print(f"  - 서울 전체 공고: {total_count:,}건")
        print(f"  - 총 페이지: {total_pages:,}페이지")
        print(f"  - 워커: 10개, 프록시: OFF (폴백 활성화)")

        # 전체 크롤링 실행
        print("\n[3] 전체 크롤링 시작...")
        print("-" * 70)

        success, job_ids, save_stats = await scraper.crawl_all(
            max_pages=None,  # 전체
            save_callback=save_jobs,
            save_batch_size=500,
        )

        end_time = datetime.now()
        elapsed = (end_time - start_time).total_seconds()

        # 결과 출력
        print("\n" + "=" * 70)
        print("크롤링 완료!")
        print("=" * 70)

        print(f"\n[결과 요약]")
        print(f"  - 목록 수집: {len(job_ids):,}개 ID")
        print(f"  - 상세 수집: {success:,}건 성공")
        print(f"  - 신규 저장: {save_stats.get('new', 0):,}건")
        print(f"  - 업데이트: {save_stats.get('updated', 0):,}건")
        print(f"  - 실패: {save_stats.get('failed', 0):,}건")
        print(f"  - 프록시 전환: {'Yes' if scraper.stats.proxy_switched else 'No'}")

        print(f"\n[시간]")
        print(f"  - 시작: {start_time.strftime('%H:%M:%S')}")
        print(f"  - 종료: {end_time.strftime('%H:%M:%S')}")
        print(f"  - 소요: {elapsed/60:.1f}분 ({elapsed:.0f}초)")
        print(f"  - 속도: {success/elapsed:.1f}건/s")

        # 저장 후 DB 상태
        print(f"\n[DB 상태]")
        stats_after = await get_job_stats()
        print(f"  - 전체 공고: {stats_after['total_jobs']:,}건 (+{stats_after['total_jobs'] - stats_before['total_jobs']:,})")
        print(f"  - 활성 공고: {stats_after['active_jobs']:,}건")

        # 크롤링 로그 저장
        await save_crawl_log({
            "started_at": start_time.isoformat(),
            "finished_at": end_time.isoformat(),
            "elapsed_seconds": int(elapsed),
            "total_ids": len(job_ids),
            "success": success,
            "new": save_stats.get("new", 0),
            "updated": save_stats.get("updated", 0),
            "failed": save_stats.get("failed", 0),
            "proxy_switched": scraper.stats.proxy_switched,
            "version": "v2",
        })
        print(f"\n[로그 저장 완료]")

    except Exception as e:
        print(f"\n[ERROR] 크롤링 실패: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await scraper.close()
        print("\n크롤러 종료")


if __name__ == "__main__":
    asyncio.run(run_full_crawl())
