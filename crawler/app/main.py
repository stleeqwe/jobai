"""크롤러 메인 실행 모듈 - V2 기반

V2 크롤러 사용:
- AJAX 엔드포인트 기반
- 적응형 폴백 (차단 시 프록시 전환)

참고: 운영 환경에서는 run_crawl_500.py 사용 권장
"""

import argparse
import asyncio
from datetime import datetime, timezone

from app.config import settings
from app.scrapers import JobKoreaScraperV2
from app.db import save_jobs, save_crawl_log, mark_expired_jobs, expire_by_deadline


async def run_full_crawl(num_workers: int = 10, max_pages: int = 250):
    """
    전체 크롤링 (V2 - AJAX 기반)

    Args:
        num_workers: 병렬 워커 수 (기본 10)
        max_pages: 최대 페이지 수 (기본 250, API 제한)
    """
    print("=" * 60)
    print(f"[{datetime.now()}] 전체 크롤링 시작 (V2)")
    print(f"모드: FULL (워커 {num_workers}개, 최대 {max_pages}페이지)")
    print(f"환경: {settings.ENVIRONMENT}")
    print("=" * 60)

    crawl_log = _init_crawl_log("full")
    start_time = datetime.now()
    scraper = JobKoreaScraperV2(
        num_workers=num_workers,
        use_proxy=False,
        fallback_to_proxy=True,
    )

    try:
        # 초기화
        await scraper.initialize()
        print(f"\n[Info] 서울 전체: {scraper.total_count:,}건")

        # V2 크롤링 (목록 + 상세, 500건마다 저장)
        print("\n[Phase 1] V2 크롤링 시작...")
        job_count, job_ids, save_result = await scraper.crawl_all(
            max_pages=max_pages,
            save_callback=save_jobs,
            save_batch_size=500,
        )
        crawl_log["total_crawled"] = job_count

        if job_count > 0:
            # 저장 결과 반영
            print(f"\n[Phase 2] 저장 완료 (총 {job_count}건)")
            _update_log_from_save(crawl_log, save_result)

            # 미등장 공고 만료 처리
            print("\n[Phase 3] 미등장 공고 만료 처리...")
            expired_missing = await mark_expired_jobs(job_ids)
            print(f"  - 미등장 만료: {expired_missing}건")

            # 마감일 기준 만료 처리
            print("\n[Phase 4] 마감일 기준 만료 처리...")
            expired_by_deadline = await expire_by_deadline()
            crawl_log["expired_jobs"] = expired_missing + expired_by_deadline
            print(f"  - 마감일 만료: {expired_by_deadline}건")

            crawl_log["status"] = "success"
        else:
            crawl_log["status"] = "partial"

        # 통계 추가
        crawl_log["stats"] = scraper.stats.summary()

    except Exception as e:
        crawl_log["status"] = "failed"
        crawl_log["error"] = str(e)
        print(f"\n[Error] 크롤링 실패: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await scraper.close()
        await _finalize_crawl(crawl_log, start_time)


# ========== 유틸리티 함수 ==========

def _init_crawl_log(mode: str) -> dict:
    """크롤링 로그 초기화"""
    return {
        "mode": mode,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "duration_seconds": None,
        "total_crawled": 0,
        "new_jobs": 0,
        "updated_jobs": 0,
        "expired_jobs": 0,
        "failed_jobs": 0,
        "status": "running",
        "error": None,
        "stats": None,
    }


def _update_log_from_save(crawl_log: dict, save_result: dict):
    """저장 결과로 로그 업데이트"""
    crawl_log["new_jobs"] = save_result.get("new", 0)
    crawl_log["updated_jobs"] = save_result.get("updated", 0)
    crawl_log["failed_jobs"] = save_result.get("failed", 0)
    print(f"  - 신규: {crawl_log['new_jobs']}건")
    print(f"  - 업데이트: {crawl_log['updated_jobs']}건")
    print(f"  - 실패: {crawl_log['failed_jobs']}건")


async def _finalize_crawl(crawl_log: dict, start_time: datetime):
    """크롤링 마무리"""
    end_time = datetime.now()
    crawl_log["finished_at"] = datetime.now(timezone.utc).isoformat()
    crawl_log["duration_seconds"] = (end_time - start_time).total_seconds()

    try:
        await save_crawl_log(crawl_log)
        print("\n[Phase 4] 크롤링 로그 저장 완료")
    except Exception as e:
        print(f"\n[Warning] 로그 저장 실패: {e}")

    # 결과 출력
    print("\n" + "=" * 60)
    print(f"[{datetime.now()}] 작업 완료")
    print(f"모드: {crawl_log['mode']}")
    print(f"상태: {crawl_log['status']}")
    print(f"소요시간: {crawl_log['duration_seconds']:.1f}초")
    print(f"처리: {crawl_log['total_crawled']}건")
    if crawl_log['new_jobs']:
        print(f"  - 신규: {crawl_log['new_jobs']}건")
    if crawl_log['updated_jobs']:
        print(f"  - 업데이트: {crawl_log['updated_jobs']}건")
    if crawl_log['expired_jobs']:
        print(f"  - 만료: {crawl_log['expired_jobs']}건")
    if crawl_log["error"]:
        print(f"에러: {crawl_log['error']}")
    print("=" * 60)


async def main():
    """CLI 진입점"""
    parser = argparse.ArgumentParser(
        description="JobChat 크롤러 V2",
        epilog="참고: 운영 환경에서는 run_crawl_500.py 사용 권장",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="병렬 워커 수 (기본 10)",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=250,
        help="최대 페이지 수 (기본 250, API 제한)",
    )

    args = parser.parse_args()
    await run_full_crawl(num_workers=args.workers, max_pages=args.pages)


if __name__ == "__main__":
    asyncio.run(main())
