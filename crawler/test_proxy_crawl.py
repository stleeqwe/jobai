#!/usr/bin/env python3
"""프록시 크롤러 테스트 스크립트 (IPRoyal 30워커)"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# 경로 설정 (상대 경로)
sys.path.insert(0, str(Path(__file__).parent))

from app.scrapers.jobkorea import JobKoreaScraper


async def test_proxy_connection():
    """프록시 연결 테스트 (1페이지만)"""
    print("=" * 60)
    print("프록시 연결 테스트")
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 프록시 3워커로 연결 테스트
    scraper = JobKoreaScraper(num_workers=3, use_proxy=True)

    try:
        # 1페이지만 크롤링
        job_count, job_ids, stats = await scraper.crawl_all_parallel(
            max_pages=1,
            save_callback=None,
        )

        print("\n" + "=" * 60)
        print("연결 테스트 결과")
        print("=" * 60)

        summary = scraper.stats.summary()
        print(f"\n[통계]")
        print(f"  - 수집된 공고: {job_count}건")
        print(f"  - 스킵: {summary['total_skipped']}건")
        print(f"  - 실패: {summary['total_failed']}건")
        print(f"  - 차단 감지: {'예' if summary['is_blocked'] else '아니오'}")

        if job_count > 0:
            print("\n[프록시 연결 성공!]")
            return True
        else:
            print("\n[프록시 연결 실패 또는 차단됨]")
            return False

    finally:
        await scraper.close()


async def main():
    """30워커 프록시 크롤링 테스트"""
    print("=" * 60)
    print("IPRoyal 프록시 30워커 크롤링 테스트")
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1단계: 프록시 연결 테스트
    print("\n[Phase 1] 프록시 연결 테스트 (3워커)...")
    connected = await test_proxy_connection()

    if not connected:
        print("\n[Error] 프록시 연결 실패. 테스트 중단.")
        return

    # 2단계: 30워커로 본격 크롤링
    print("\n" + "=" * 60)
    print("[Phase 2] 30워커 프록시 크롤링")
    print("=" * 60)

    scraper = JobKoreaScraper(num_workers=30, use_proxy=True)

    try:
        # 5페이지만 테스트 (약 2,500건)
        job_count, job_ids, stats = await scraper.crawl_all_parallel(
            max_pages=5,
            save_callback=None,  # 저장 없이 테스트
        )

        print("\n" + "=" * 60)
        print("30워커 크롤링 결과")
        print("=" * 60)

        summary = scraper.stats.summary()
        print(f"\n[통계]")
        print(f"  - 수집된 공고: {job_count}건")
        print(f"  - 스킵: {summary['total_skipped']}건")
        print(f"  - 실패: {summary['total_failed']}건")
        print(f"  - 차단 감지: {'예' if summary['is_blocked'] else '아니오'}")
        print(f"  - 소요 시간: {summary['elapsed_seconds']}초 ({summary['elapsed_minutes']}분)")

        # 속도 계산
        if summary['elapsed_seconds'] > 0:
            rate = job_count / summary['elapsed_seconds']
            print(f"  - 크롤링 속도: {rate:.1f}건/초")

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
