#!/usr/bin/env python3
"""전체 크롤링 스크립트 (30워커 + 프록시 + Firestore 저장)"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.scrapers.jobkorea import JobKoreaScraper
from app.db import save_jobs, mark_expired_jobs, expire_by_deadline


async def main():
    print("=" * 70)
    print("전체 크롤링 시작 (30워커 + IPRoyal 프록시)")
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 30워커 + 프록시 활성화
    scraper = JobKoreaScraper(num_workers=30, use_proxy=True)

    try:
        # 전체 크롤링 (125페이지 예상, 여유있게 150페이지)
        print("\n[Phase 1] 병렬 크롤링...")
        job_count, job_ids, save_stats = await scraper.crawl_all_parallel(
            max_pages=150,
            save_callback=save_jobs,
            save_batch_size=500,
        )

        print("\n" + "=" * 70)
        print("[Phase 1 완료] 크롤링 결과")
        print("=" * 70)

        stats = scraper.stats.summary()
        print(f"  - 수집: {job_count}건")
        print(f"  - 스킵: {stats['total_skipped']}건")
        print(f"  - 실패: {stats['total_failed']}건")
        print(f"  - 저장: 신규 {save_stats.get('new', 0)}건, 업데이트 {save_stats.get('updated', 0)}건")
        print(f"  - 소요 시간: {stats['elapsed_minutes']}분")
        print(f"  - 차단 감지: {'예' if stats['is_blocked'] else '아니오'}")

        if job_count > 0:
            # 미등장 공고 만료 처리
            print("\n[Phase 2] 미등장 공고 만료 처리...")
            expired_missing = await mark_expired_jobs(job_ids)
            print(f"  - 미등장 만료: {expired_missing}건")

            # 마감일 기준 만료 처리
            print("\n[Phase 3] 마감일 기준 만료 처리...")
            expired_deadline = await expire_by_deadline()
            print(f"  - 마감일 만료: {expired_deadline}건")

        print("\n" + "=" * 70)
        print("전체 크롤링 완료!")
        print(f"종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)

    except KeyboardInterrupt:
        print("\n[중단] 사용자에 의해 중단됨")
    except Exception as e:
        print(f"\n[Error] 크롤링 실패: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
