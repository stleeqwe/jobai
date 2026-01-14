#!/usr/bin/env python3
"""
서울시 전체 채용공고 크롤링 스크립트
- 워커 2개, 병렬 5개, 딜레이 1초
- 10페이지씩 배치 처리, 배치 간 10분 휴식
- 30일 이내 공고만 수집
"""
import asyncio
import sys
from datetime import datetime
from google.cloud import firestore

sys.path.insert(0, '/Users/stlee/Desktop/jobbot/jobai/crawler')
from app.scrapers.jobkorea import JobKoreaScraper
from app.db.firestore import save_jobs

# 설정
PAGES_PER_BATCH = 5       # 배치당 페이지 수
REST_MINUTES = 5          # 배치 간 휴식 시간 (분)
MAX_PAGES = 100           # 최대 페이지 (안전장치, 필요시 늘림)
NUM_WORKERS = 2           # 워커 수

# Firestore 클라이언트
db = firestore.Client(project='jobchat-1768149763')


def get_db_count():
    """현재 DB의 서울 공고 수"""
    return db.collection('jobs').where('location_sido', '==', '서울').count().get()[0][0].value


async def main():
    start_time = datetime.now()
    print("=" * 60, flush=True)
    print("서울시 전체 채용공고 크롤링", flush=True)
    print("=" * 60, flush=True)
    print(f"시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"설정: 워커 {NUM_WORKERS}개, 배치 {PAGES_PER_BATCH}페이지, 휴식 {REST_MINUTES}분", flush=True)
    print(f"초기 DB 공고 수: {get_db_count()}건", flush=True)
    print("=" * 60, flush=True)

    total_collected = 0
    total_skipped = 0
    total_saved = {"new": 0, "updated": 0}
    batch_num = 0
    current_page = 1

    while current_page <= MAX_PAGES:
        batch_num += 1
        batch_start = datetime.now()
        end_page = min(current_page + PAGES_PER_BATCH - 1, MAX_PAGES)

        print(f"\n[배치 {batch_num}] 페이지 {current_page}~{end_page} 크롤링 시작", flush=True)
        print("-" * 40, flush=True)

        # 크롤러 생성 (매 배치마다 새로 생성)
        scraper = JobKoreaScraper(num_workers=NUM_WORKERS)

        try:
            # 저장 콜백
            async def save_callback(jobs):
                # 서울 공고만 필터링
                seoul_jobs = [j for j in jobs if j.get('location_sido') == '서울']
                if seoul_jobs:
                    result = await save_jobs(seoul_jobs)
                    return result
                return {'new': 0, 'updated': 0}

            # 크롤링 실행
            batch_count, batch_ids, save_result = await scraper.crawl_all_parallel(
                max_pages=PAGES_PER_BATCH,
                start_page=current_page,
                save_callback=save_callback,
                save_batch_size=500
            )

            # 통계 업데이트
            batch_collected = batch_count
            batch_skipped = scraper.stats.total_skipped
            total_collected += batch_collected
            total_skipped += batch_skipped
            total_saved["new"] += save_result.get("new", 0)
            total_saved["updated"] += save_result.get("updated", 0)

            batch_elapsed = (datetime.now() - batch_start).total_seconds() / 60

            print(f"\n[배치 {batch_num}] 완료", flush=True)
            print(f"  수집: {batch_collected}건, 스킵: {batch_skipped}건", flush=True)
            print(f"  저장: 신규 {save_result.get('new', 0)}건, 업데이트 {save_result.get('updated', 0)}건", flush=True)
            print(f"  소요: {batch_elapsed:.1f}분", flush=True)
            print(f"  DB 총: {get_db_count()}건", flush=True)

            # 차단 감지 시 중단
            if scraper.stats.is_blocked():
                print("\n[경고] 차단 감지! 크롤링 중단", flush=True)
                break

            # 공고가 없으면 종료
            if batch_collected == 0 and batch_skipped == 0:
                print("\n[완료] 더 이상 공고 없음", flush=True)
                break

        finally:
            await scraper.close()

        # 다음 배치 준비
        current_page += PAGES_PER_BATCH

        # 마지막 배치가 아니면 휴식
        if current_page <= MAX_PAGES:
            print(f"\n[휴식] {REST_MINUTES}분 대기 중...", flush=True)
            for i in range(REST_MINUTES, 0, -1):
                print(f"  {i}분 남음...", flush=True)
                await asyncio.sleep(60)
            print(f"  휴식 완료!", flush=True)

    # 최종 결과
    total_elapsed = (datetime.now() - start_time).total_seconds() / 60

    print("\n" + "=" * 60, flush=True)
    print("크롤링 완료", flush=True)
    print("=" * 60, flush=True)
    print(f"총 소요 시간: {total_elapsed:.1f}분 ({total_elapsed/60:.1f}시간)", flush=True)
    print(f"총 수집 (30일 이내): {total_collected}건", flush=True)
    print(f"총 스킵 (30일 이전): {total_skipped}건", flush=True)
    print(f"DB 저장: 신규 {total_saved['new']}건, 업데이트 {total_saved['updated']}건", flush=True)
    print(f"최종 DB 공고 수: {get_db_count()}건", flush=True)
    print("=" * 60, flush=True)


if __name__ == '__main__':
    asyncio.run(main())
