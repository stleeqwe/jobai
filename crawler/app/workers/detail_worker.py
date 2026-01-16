"""
상세 페이지 크롤링 오케스트레이터

crawl_details() 로직을 캡슐화하여 관리 용이성 향상.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional, Callable, Awaitable, TYPE_CHECKING

from app.logging_config import get_logger

if TYPE_CHECKING:
    from app.scrapers.jobkorea_v2 import JobKoreaScraperV2

logger = get_logger("crawler.worker")


@dataclass
class CrawlState:
    """크롤링 상태 관리"""
    total: int = 0
    completed: int = 0
    retry_round: int = 0

    # 저장 통계
    total_saved: Dict[str, int] = field(default_factory=lambda: {"new": 0, "updated": 0, "failed": 0})

    # 진행 추적
    start_time: float = 0.0
    last_check_time: float = 0.0
    last_completed: int = 0
    progress_every: int = 100
    next_progress: int = 100

    # 재시도 관리
    attempts: Dict[str, int] = field(default_factory=dict)
    pending_jobs: List[Dict] = field(default_factory=list)

    def init(self, job_ids: List[str]):
        """상태 초기화"""
        self.total = len(job_ids)
        self.completed = 0
        self.retry_round = 0
        self.start_time = time.time()
        self.last_check_time = self.start_time
        self.last_completed = 0
        self.next_progress = self.progress_every
        self.attempts = {job_id: 0 for job_id in job_ids}
        self.pending_jobs = []
        self.total_saved = {"new": 0, "updated": 0, "failed": 0}


class DetailCrawlOrchestrator:
    """상세 페이지 크롤링 오케스트레이터"""

    def __init__(
        self,
        scraper: "JobKoreaScraperV2",
        batch_size: int = 500,
        parallel_batch: int = 10,
        retry_limit: int = 2,
        retry_backoff: float = 1.5,
        min_parallel_batch: int = 3,
    ):
        """
        Args:
            scraper: 부모 스크래퍼 인스턴스
            batch_size: 저장 배치 크기
            parallel_batch: 동시 워커 수
            retry_limit: 실패 재시도 횟수
            retry_backoff: 재시도 라운드 딜레이 배수
            min_parallel_batch: 재시도 시 최소 동시 요청 수
        """
        self.scraper = scraper
        self.batch_size = batch_size
        self.parallel_batch = parallel_batch
        self.retry_limit = retry_limit
        self.retry_backoff = retry_backoff
        self.min_parallel_batch = min_parallel_batch

        self.state = CrawlState()
        self.save_callback: Optional[Callable[[List[Dict]], Awaitable[dict]]] = None

    async def run(
        self,
        job_ids: Set[str],
        save_callback: Optional[Callable[[List[Dict]], Awaitable[dict]]] = None,
    ) -> Tuple[int, Dict]:
        """
        상세 페이지 크롤링 실행

        Args:
            job_ids: 수집할 Job ID 세트
            save_callback: 저장 콜백

        Returns:
            (성공 건수, 저장 통계)
        """
        logger.info(f"상세 수집 시작: {len(job_ids):,}건")
        print(f"[V2] 상세 수집 시작: {len(job_ids):,}건", flush=True)

        self.save_callback = save_callback
        id_list = list(job_ids)
        self.state.init(id_list)

        current_parallel = min(self.parallel_batch, self.scraper.num_workers)
        min_parallel = min(current_parallel, self.min_parallel_batch)
        pending_ids: List[str] = id_list

        while pending_ids:
            retry_queue = await self._run_round(pending_ids, current_parallel)

            if retry_queue:
                self.state.retry_round += 1
                current_parallel = max(min_parallel, current_parallel - 1)
                self._adjust_rate_limit()
                print(
                    f"[V2] 재시도 라운드 {self.state.retry_round}: {len(retry_queue)}건, "
                    f"parallel={current_parallel}, delay={self.scraper.rate_limiter.delay:.2f}s",
                    flush=True,
                )

            pending_ids = retry_queue

        # 남은 데이터 저장
        await self._flush_pending_jobs(force=True)

        logger.info(
            f"상세 수집 완료: 성공 {self.scraper.stats.detail_success}, "
            f"실패 {self.scraper.stats.detail_failed}"
        )
        return self.scraper.stats.detail_success, self.state.total_saved

    async def _run_round(
        self,
        pending_ids: List[str],
        current_parallel: int,
    ) -> List[str]:
        """한 라운드의 크롤링 실행"""
        active_workers = min(current_parallel, self.scraper.num_workers, len(pending_ids))
        results_queue: asyncio.Queue = asyncio.Queue()
        chunks = [pending_ids[i::active_workers] for i in range(active_workers)]

        # 워커 태스크 생성
        workers = [
            asyncio.create_task(self._detail_worker(i, chunks[i], results_queue))
            for i in range(active_workers)
        ]

        # 결과 수집 태스크 생성
        collector = asyncio.create_task(
            self._collect_results(results_queue, active_workers)
        )

        await asyncio.gather(*workers)
        return await collector

    async def _detail_worker(
        self,
        worker_idx: int,
        ids: List[str],
        results_queue: asyncio.Queue,
    ) -> None:
        """개별 워커: 할당된 ID 목록 처리"""
        try:
            for job_id in ids:
                try:
                    result = await self.scraper._fetch_detail_with_fallback(job_id, worker_idx)
                except Exception as e:
                    logger.warning("상세 워커 %d 실패 (%s): %s", worker_idx, job_id, e)
                    result = None
                await results_queue.put((job_id, result))
                await asyncio.sleep(self.scraper.rate_limiter.get_delay())
        finally:
            await results_queue.put((None, None))

    async def _collect_results(
        self,
        results_queue: asyncio.Queue,
        active_workers: int,
    ) -> List[str]:
        """결과 수집 및 처리"""
        retry_queue: List[str] = []
        finished_workers = 0

        while finished_workers < active_workers:
            job_id, result = await results_queue.get()

            if job_id is None:
                finished_workers += 1
                continue

            await self._process_result(job_id, result, retry_queue)

            # 배치 저장
            if self.save_callback and len(self.state.pending_jobs) >= self.batch_size:
                await self._flush_pending_jobs()

            # 진행 상황 출력
            await self._report_progress()

        return retry_queue

    async def _process_result(
        self,
        job_id: str,
        result: Optional[Dict],
        retry_queue: List[str],
    ) -> None:
        """개별 결과 처리"""
        if isinstance(result, dict) and result:
            if result.get("_not_found"):
                # 404 (삭제된 공고) - 재시도 없이 스킵
                self.scraper.stats.detail_not_found += 1
                self.state.completed += 1
            else:
                self.state.pending_jobs.append(result)
                self.scraper.stats.detail_success += 1
                self.state.completed += 1
        else:
            self.state.attempts[job_id] += 1
            if self.state.attempts[job_id] <= self.retry_limit:
                retry_queue.append(job_id)
            else:
                self.scraper.stats.detail_failed += 1
                self.state.total_saved["failed"] += 1
                self.state.completed += 1

    async def _report_progress(self) -> None:
        """진행 상황 보고"""
        state = self.state

        if state.completed < state.next_progress and state.completed != state.total:
            return

        now = time.time()
        elapsed = now - state.start_time
        speed = state.completed / elapsed if elapsed > 0 else 0
        eta = (state.total - state.completed) / speed if speed > 0 else 0

        print(
            f"[V2] 진행: {state.completed}/{state.total} "
            f"({speed:.1f}건/s, ETA: {eta/60:.1f}분)",
            flush=True,
        )

        # 윈도우 속도 계산 및 프록시 풀 전환 판단
        window_completed = state.completed - state.last_completed
        window_elapsed = now - state.last_check_time
        window_speed = window_completed / window_elapsed if window_elapsed > 0 else 0

        state.last_completed = state.completed
        state.last_check_time = now

        if state.completed >= state.next_progress:
            state.next_progress = ((state.completed // state.progress_every) + 1) * state.progress_every

        await self.scraper._maybe_switch_to_proxy_pool(window_speed, state.completed)

    async def _flush_pending_jobs(self, force: bool = False) -> None:
        """대기 중인 작업 저장"""
        if not self.save_callback or not self.state.pending_jobs:
            return

        pending_jobs = self.state.pending_jobs
        batch_size = self.batch_size

        while pending_jobs and (force or len(pending_jobs) >= batch_size):
            batch = pending_jobs if force else pending_jobs[:batch_size]
            try:
                result = await self.save_callback(batch)
                self.state.total_saved["new"] += result.get("new", 0)
                self.state.total_saved["updated"] += result.get("updated", 0)

                if force:
                    print(f"[V2] 최종 저장: {len(batch)}건", flush=True)
                else:
                    print(f"[V2] 저장: {len(batch)}건", flush=True)

                del pending_jobs[:len(batch)]
            except Exception as e:
                logger.error(f"저장 실패: {e}")
                break

            if force:
                break

    def _adjust_rate_limit(self) -> None:
        """재시도 시 레이트 리밋 조정"""
        rate_limiter = self.scraper.rate_limiter
        new_delay = min(rate_limiter.max_delay, rate_limiter.delay * self.retry_backoff)
        rate_limiter.delay = new_delay
        rate_limiter.min_delay = max(rate_limiter.min_delay, new_delay)
