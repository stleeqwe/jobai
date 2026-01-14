"""크롤러 메인 실행 모듈 - 다중 모드 지원"""

import argparse
import asyncio
from datetime import datetime, timezone, timedelta

from app.config import settings
from app.scrapers import JobKoreaScraper
from app.db import (
    save_jobs, save_crawl_log, mark_expired_jobs,
    expire_by_deadline, get_jobs_for_verification, mark_jobs_expired
)


async def run_full_crawl(num_workers: int = 3):
    """
    전체 크롤링 (최초 1회 또는 전체 갱신)

    Args:
        num_workers: 병렬 워커 수 (기본 3)
    """
    print("=" * 60)
    print(f"[{datetime.now()}] 전체 크롤링 시작")
    print(f"모드: FULL (병렬 {num_workers} 워커)")
    print(f"환경: {settings.ENVIRONMENT}")
    print("=" * 60)

    crawl_log = _init_crawl_log("full")
    start_time = datetime.now()
    scraper = JobKoreaScraper(num_workers=num_workers)

    try:
        # 병렬 크롤링 (500건마다 중간 저장)
        print("\n[Phase 1] 병렬 크롤링 시작 (500건마다 중간 저장)...")
        job_count, job_ids, save_result = await scraper.crawl_all_parallel(
            save_callback=save_jobs,
            save_batch_size=500
        )
        crawl_log["total_crawled"] = job_count

        if job_count > 0:
            # 저장 결과 반영 (이미 중간 저장됨)
            print(f"\n[Phase 2] 저장 완료 (총 {job_count}건)")
            _update_log_from_save(crawl_log, save_result)

            # 미등장 공고 만료 처리 (크롤링에서 발견되지 않은 공고)
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


async def run_hourly_update(count: int = 200):
    """
    매시간 증분 업데이트

    Args:
        count: 수집할 최신 공고 수 (기본 200, 피크시간 500)
    """
    # 피크 시간 체크 (평일 09-11시)
    now = datetime.now()
    is_peak = now.weekday() < 5 and 9 <= now.hour < 11
    if is_peak:
        count = max(count, 500)
        print(f"[Info] 피크 시간대 감지, 수집량 증가: {count}건")

    print("=" * 60)
    print(f"[{datetime.now()}] 증분 업데이트 시작")
    print(f"모드: HOURLY (최신 {count}건)")
    print("=" * 60)

    crawl_log = _init_crawl_log("hourly")
    start_time = datetime.now()
    scraper = JobKoreaScraper(num_workers=1)

    try:
        # 최신 공고 수집
        print("\n[Phase 1] 최신 공고 수집...")
        jobs = await scraper.crawl_latest(count=count)
        crawl_log["total_crawled"] = len(jobs)

        if jobs:
            # DB 저장 (upsert)
            print(f"\n[Phase 2] DB 저장 ({len(jobs)}건)...")
            save_result = await save_jobs(jobs)
            _update_log_from_save(crawl_log, save_result)

        # 마감일 기준 자동 만료 처리
        print("\n[Phase 3] 마감일 기준 만료 처리...")
        expired_count = await expire_by_deadline()
        crawl_log["expired_jobs"] = expired_count
        print(f"  - 마감일 만료: {expired_count}건")

        crawl_log["status"] = "success"

    except Exception as e:
        crawl_log["status"] = "failed"
        crawl_log["error"] = str(e)
        print(f"\n[Error] 업데이트 실패: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await scraper.close()
        await _finalize_crawl(crawl_log, start_time)


async def run_daily_verification():
    """
    매일 새벽 URL 검증 (활성 공고의 15% 검증)
    """
    print("=" * 60)
    print(f"[{datetime.now()}] 일일 검증 시작")
    print(f"모드: DAILY VERIFICATION")
    print("=" * 60)

    crawl_log = _init_crawl_log("daily_verification")
    start_time = datetime.now()
    scraper = JobKoreaScraper(num_workers=1)

    try:
        # 검증 대상 조회 (7일 이상 미검증 + 상시채용 90일 이상)
        print("\n[Phase 1] 검증 대상 조회...")
        job_ids = await get_jobs_for_verification(
            days_since_verified=7,  # 7일간 미검증
            max_count=10000,  # 최대 1만건
        )
        print(f"  - 검증 대상: {len(job_ids)}건")

        if job_ids:
            # URL 검증 (HEAD 요청)
            print("\n[Phase 2] URL 검증...")
            results = await scraper.verify_jobs(job_ids)

            # 만료된 공고 처리
            expired_ids = [jid for jid, valid in results.items() if not valid]
            if expired_ids:
                print(f"\n[Phase 3] 만료 공고 처리 ({len(expired_ids)}건)...")
                await mark_jobs_expired(expired_ids)

            crawl_log["total_crawled"] = len(job_ids)
            crawl_log["expired_jobs"] = len(expired_ids)

        crawl_log["status"] = "success"

    except Exception as e:
        crawl_log["status"] = "failed"
        crawl_log["error"] = str(e)
        print(f"\n[Error] 검증 실패: {e}")
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
    parser = argparse.ArgumentParser(description="JobChat 크롤러")
    parser.add_argument(
        "--mode",
        choices=["full", "hourly", "daily"],
        default="hourly",
        help="크롤링 모드 (full: 전체, hourly: 증분, daily: 검증)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="병렬 워커 수 (full 모드, 기본 3)"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=200,
        help="수집 건수 (hourly 모드, 기본 200)"
    )

    args = parser.parse_args()

    if args.mode == "full":
        await run_full_crawl(num_workers=args.workers)
    elif args.mode == "hourly":
        await run_hourly_update(count=args.count)
    elif args.mode == "daily":
        await run_daily_verification()


if __name__ == "__main__":
    asyncio.run(main())
