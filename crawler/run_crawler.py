#!/usr/bin/env python3
"""JobBot 크롤러 - 서울시 전체 채용공고 수집

메인 크롤러 스크립트:
- 구별 분할 크롤링으로 API 250페이지 제한 우회
- 강남구(16,000+건)는 jobtype+career 조합으로 추가 분할
- 프록시 풀 모드로 안정적 수집
- --skip-existing 옵션으로 증분 크롤링 지원

사용법:
    python run_crawler.py                 # 전체 크롤링
    python run_crawler.py --skip-existing # 신규 공고만 크롤링
    python run_crawler.py --list-only     # 목록만 수집 (상세 스킵)
"""

import argparse
import asyncio
import sys
import os
from datetime import datetime
from typing import Set, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.scrapers.jobkorea_v2 import JobKoreaScraperV2
from app.core.ajax_client import AdaptiveRateLimiter
from app.db.firestore import save_jobs, get_job_stats, save_crawl_log, get_existing_job_ids
from app.logging_config import get_logger

logger = get_logger("crawler.gu")

# 서울시 25개 구 코드
SEOUL_GU_CODES = {
    "강남구": "I010", "서초구": "I020", "송파구": "I030", "강동구": "I040",
    "마포구": "I050", "영등포구": "I060", "용산구": "I070", "종로구": "I080",
    "중구": "I090", "성동구": "I100", "광진구": "I110", "동대문구": "I120",
    "중랑구": "I130", "성북구": "I140", "강북구": "I150", "도봉구": "I160",
    "노원구": "I170", "은평구": "I180", "서대문구": "I190", "양천구": "I200",
    "강서구": "I210", "구로구": "I220", "금천구": "I230", "동작구": "I240",
    "관악구": "I250",
}

# 강남구 분할 쿼리 (10,000건 초과 대응)
GANGNAM_SPLIT_QUERIES = [
    {"name": "정규직+신입", "jobtype": "1", "career": "1"},
    {"name": "정규직+경력", "jobtype": "1", "career": "2"},
    {"name": "정규직+경력무관", "jobtype": "1", "career": "3"},
    {"name": "계약직", "jobtype": "2"},
    {"name": "파견직", "jobtype": "3"},
    {"name": "위촉직", "jobtype": "4"},
    {"name": "인턴", "jobtype": "5"},
    {"name": "아르바이트", "jobtype": "10"},
]


async def crawl_gu(gu_name: str, gu_code: str, all_ids: Set[str]) -> int:
    """단일 구 크롤링 (강남구는 분할 처리)"""
    import re

    # 강남구는 분할 크롤링 (10,000건 초과 대응)
    if gu_code == "I010":
        return await crawl_gangnam_split(gu_code, all_ids)

    scraper = JobKoreaScraperV2(num_workers=5, use_proxy=False, fallback_to_proxy=True)

    try:
        await scraper.initialize()

        # 해당 구의 총 공고 수 확인
        resp = await scraper.clients[0].get(
            "https://www.jobkorea.co.kr/Recruit/Home/_GI_List",
            params={"Page": 1, "local": gu_code},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        match = re.search(r'hdnGICnt.*?value="([\d,]+)"', resp.text)
        total_count = int(match.group(1).replace(",", "")) if match else 0

        if total_count == 0:
            print(f"[{gu_name}] 공고 없음, 건너뜀")
            return 0

        max_pages = min(250, (total_count // 40) + 1)
        print(f"[{gu_name}] {total_count:,}건 ({max_pages}페이지)")

        # 목록 수집 (local 파라미터 지정)
        collected_ids = await crawl_list_with_params(scraper, {"local": gu_code}, max_pages)

        before_count = len(all_ids)
        all_ids.update(collected_ids)
        new_count = len(all_ids) - before_count

        print(f"[{gu_name}] 완료: {len(collected_ids)}개 수집, {new_count}개 신규")

        return len(collected_ids)

    finally:
        await scraper.close()


async def crawl_gangnam_split(gu_code: str, all_ids: Set[str]) -> int:
    """강남구 분할 크롤링 (jobtype+career 조합)"""
    import re

    print(f"[강남구] 분할 크롤링 시작 (10,000건 초과 대응)")

    scraper = JobKoreaScraperV2(num_workers=5, use_proxy=False, fallback_to_proxy=True)
    total_collected = 0

    try:
        await scraper.initialize()

        for query in GANGNAM_SPLIT_QUERIES:
            params = {"local": gu_code}
            if "jobtype" in query:
                params["jobtype"] = query["jobtype"]
            if "career" in query:
                params["career"] = query["career"]

            # 해당 쿼리의 공고 수 확인
            resp = await scraper.clients[0].get(
                "https://www.jobkorea.co.kr/Recruit/Home/_GI_List",
                params={"Page": 1, **params},
                headers={"X-Requested-With": "XMLHttpRequest"}
            )
            match = re.search(r'hdnGICnt.*?value="([\d,]+)"', resp.text)
            count = int(match.group(1).replace(",", "")) if match else 0

            if count == 0:
                print(f"  [{query['name']}] 공고 없음, 건너뜀")
                continue

            max_pages = min(250, (count // 40) + 1)
            print(f"  [{query['name']}] {count:,}건 ({max_pages}페이지)")

            # 목록 수집
            collected_ids = await crawl_list_with_params(scraper, params, max_pages)

            before_count = len(all_ids)
            all_ids.update(collected_ids)
            new_count = len(all_ids) - before_count

            print(f"  [{query['name']}] 완료: {len(collected_ids)}개, 신규 {new_count}개")
            total_collected += len(collected_ids)

            await asyncio.sleep(0.5)  # 쿼리 간 간격

        print(f"[강남구] 분할 크롤링 완료: 총 {total_collected:,}개 (중복 제거 후 {len(all_ids):,}개)")
        return total_collected

    finally:
        await scraper.close()


async def crawl_list_with_params(scraper: JobKoreaScraperV2, params: Dict, max_pages: int) -> Set[str]:
    """파라미터로 목록 수집 (local, jobtype, career 등)"""
    import re
    collected_ids: Set[str] = set()
    rate_limiter = AdaptiveRateLimiter()
    no_new_pages = 0
    repeat_pages = 0
    last_page_ids: Optional[Set[str]] = None

    for page in range(1, max_pages + 1):
        try:
            client = scraper.clients[page % len(scraper.clients)]
            resp = await client.get(
                "https://www.jobkorea.co.kr/Recruit/Home/_GI_List",
                params={"Page": page, **params},
                headers={"X-Requested-With": "XMLHttpRequest"}
            )

            if resp.status_code == 200:
                page_ids = set(re.findall(r'GI_Read/(\d+)', resp.text))
                new_ids = page_ids - collected_ids
                collected_ids.update(page_ids)

                if not new_ids:
                    no_new_pages += 1
                else:
                    no_new_pages = 0

                if last_page_ids is not None and page_ids == last_page_ids:
                    repeat_pages += 1
                else:
                    repeat_pages = 0
                last_page_ids = page_ids

                if repeat_pages >= 2 or no_new_pages >= 3:
                    logger.warning(f"중복 페이지 감지로 조기 종료: 페이지 {page}")
                    break

                rate_limiter.on_success()
            else:
                logger.warning(f"AJAX 호출 실패: 페이지 {page}, 상태 {resp.status_code}")
                rate_limiter.on_error(resp.status_code)

            if page % 50 == 0:
                print(f"    페이지 {page}/{max_pages}: 누적 {len(collected_ids)}개")

            await asyncio.sleep(rate_limiter.get_delay())

        except Exception as e:
            logger.warning(f"페이지 {page} 실패: {e}")
            await asyncio.sleep(rate_limiter.get_delay())

    return collected_ids


async def run_crawler(skip_existing: bool = False, list_only: bool = False):
    """
    메인 크롤링 실행

    Args:
        skip_existing: True면 DB에 있는 공고 상세 크롤링 스킵
        list_only: True면 목록만 수집하고 상세 크롤링 스킵
    """
    start_time = datetime.now()

    print("=" * 70)
    print("JobBot 크롤러 - 서울시 전체 채용공고 수집")
    print(f"시작: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"모드: {'증분 (신규만)' if skip_existing else '전체'}")
    if list_only:
        print("주의: 목록만 수집 (상세 크롤링 스킵)")
    print("=" * 70)

    # DB 상태
    stats_before = await get_job_stats()
    print(f"\n[DB] 현재: {stats_before['total_jobs']:,}건, 활성: {stats_before['active_jobs']:,}건")

    # 전체 ID 수집
    all_ids: Set[str] = set()
    gu_stats: Dict[str, int] = {}

    # 구별 순차 크롤링 (병렬은 차단 위험)
    print("\n[Phase 1] 목록 수집 (구별)")
    for gu_name, gu_code in SEOUL_GU_CODES.items():
        try:
            count = await crawl_gu(gu_name, gu_code, all_ids)
            gu_stats[gu_name] = count
            print(f"[진행] 전체 고유 ID: {len(all_ids):,}개\n")
        except Exception as e:
            print(f"[{gu_name}] 오류: {e}")
            gu_stats[gu_name] = 0

    print("=" * 70)
    print(f"목록 수집 완료: {len(all_ids):,}개 고유 ID")
    print("=" * 70)

    # 목록만 수집 모드
    if list_only:
        print("\n[완료] 목록만 수집 모드 - 상세 크롤링 스킵")
        return

    # 기존 공고 스킵 처리
    skipped_count = 0
    if skip_existing and all_ids:
        print("\n[Phase 2] 기존 공고 필터링...")
        existing_ids = await get_existing_job_ids()
        original_count = len(all_ids)
        all_ids = all_ids - existing_ids
        skipped_count = original_count - len(all_ids)
        print(f"  - 기존 공고: {len(existing_ids):,}건")
        print(f"  - 스킵: {skipped_count:,}건")
        print(f"  - 신규 크롤링 대상: {len(all_ids):,}건")

    # 상세 수집
    if all_ids:
        phase_num = 3 if skip_existing else 2
        print(f"\n[Phase {phase_num}] 상세 수집: {len(all_ids):,}건")

        scraper = JobKoreaScraperV2(
            num_workers=30,
            use_proxy=True,
            fallback_to_proxy=True,
            proxy_pool_size=30,
            proxy_start_pool=True,
            proxy_pool_warmup=True,
            proxy_worker_rotate_threshold=2,
            proxy_session_lifetime="30m",
            proxy_speed_threshold=2.0,
            proxy_delay_threshold=1.0,
            proxy_speed_consecutive=3,
            proxy_speed_warmup=500,
        )
        try:
            await scraper.initialize()
            scraper.rate_limiter.min_delay = 0.3  # 차단 방지 (보수적)
            scraper.rate_limiter.delay = 0.5
            success, save_stats = await scraper.crawl_details(
                all_ids,
                save_callback=save_jobs,
                batch_size=500,
                parallel_batch=30,  # 10 프록시 × 3 동시요청
                retry_limit=3,
                retry_backoff=1.5,
                min_parallel_batch=10,  # 최소 프록시당 1개
            )
            # 통계 캡처 (close 전에)
            crawl_stats = scraper.stats.summary()
        finally:
            await scraper.close()

        end_time = datetime.now()
        elapsed = (end_time - start_time).total_seconds()

        print("\n" + "=" * 70)
        print("크롤링 완료!")
        print("=" * 70)
        print(f"\n[결과]")
        print(f"  - 목록 수집: {len(all_ids) + skipped_count:,}개")
        if skipped_count:
            print(f"  - 스킵 (기존): {skipped_count:,}건")
        print(f"  - 상세 성공: {success:,}건")
        print(f"  - 신규 저장: {save_stats.get('new', 0):,}건")
        print(f"  - 업데이트: {save_stats.get('updated', 0):,}건")
        print(f"  - 소요: {elapsed/60:.1f}분 ({success/elapsed:.1f}건/s)")

        # 차단/레이트리밋 통계
        if crawl_stats.get("block_count") or crawl_stats.get("rate_limit_count") or crawl_stats.get("error_403_count"):
            print(f"\n[차단 통계]")
            if crawl_stats.get("block_count"):
                print(f"  - 차단 감지: {crawl_stats['block_count']}회")
            if crawl_stats.get("rate_limit_count"):
                print(f"  - 레이트리밋 (429): {crawl_stats['rate_limit_count']}회")
            if crawl_stats.get("error_403_count"):
                print(f"  - 접근거부 (403): {crawl_stats['error_403_count']}회")

        # DB 상태
        stats_after = await get_job_stats()
        print(f"\n[DB] 결과: {stats_after['total_jobs']:,}건 (+{stats_after['total_jobs'] - stats_before['total_jobs']:,})")

        # 로그 저장
        await save_crawl_log({
            "started_at": start_time.isoformat(),
            "finished_at": end_time.isoformat(),
            "elapsed_seconds": int(elapsed),
            "total_ids": len(all_ids) + skipped_count,
            "skipped": skipped_count,
            "success": success,
            "new": save_stats.get("new", 0),
            "updated": save_stats.get("updated", 0),
            "version": "v2",
            "mode": "incremental" if skip_existing else "full",
            "gu_stats": gu_stats,
            # 차단/레이트리밋 통계
            "block_count": crawl_stats.get("block_count", 0),
            "rate_limit_count": crawl_stats.get("rate_limit_count", 0),
            "error_403_count": crawl_stats.get("error_403_count", 0),
        })
    else:
        print("\n[완료] 크롤링할 신규 공고 없음")


def main():
    """CLI 진입점"""
    parser = argparse.ArgumentParser(
        description="JobBot 크롤러 - 서울시 전체 채용공고 수집",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python run_crawler.py                 # 전체 크롤링
  python run_crawler.py --skip-existing # 신규 공고만 (증분 크롤링)
  python run_crawler.py --list-only     # 목록만 수집
        """
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="DB에 있는 공고는 상세 크롤링 스킵 (증분 모드)",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="목록만 수집하고 상세 크롤링 스킵",
    )

    args = parser.parse_args()
    asyncio.run(run_crawler(
        skip_existing=args.skip_existing,
        list_only=args.list_only,
    ))


if __name__ == "__main__":
    main()
