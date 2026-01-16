"""
잡코리아 크롤러 V2 Lite
- AJAX 엔드포인트 사용으로 페이지네이션 정상 작동
- 적응형 폴백: 프록시 없이 시작 → 차단 시 프록시 전환
"""

import asyncio
import random
import time
from datetime import datetime
from typing import Optional, List, Dict, Set, Tuple, Callable, Awaitable

import httpx

from app.config import CrawlerConfig, settings, USER_AGENTS
from app.core.session_manager import SessionManager, ProxySessionManager
from app.core.ajax_client import AjaxClient, AdaptiveRateLimiter, BlockedError
from app.normalizers.dedup import DedupKeyGenerator
from app.parsers.detail_parser import DetailPageParser
from app.workers.detail_worker import DetailCrawlOrchestrator
from app.logging_config import get_logger

logger = get_logger("crawler.v2")


class CrawlerStats:
    """크롤링 통계"""

    def __init__(self):
        self.list_pages = 0
        self.list_ids = 0
        self.detail_success = 0
        self.detail_failed = 0
        self.detail_not_found = 0  # 404 (삭제된 공고)
        self.proxy_switched = False
        self.start_time = None
        self.errors = []
        # 차단/레이트리밋 추적
        self.block_count = 0  # 차단 감지 횟수
        self.rate_limit_count = 0  # 429 응답 횟수
        self.error_403_count = 0  # 403 응답 횟수

    def summary(self) -> dict:
        elapsed = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        return {
            "list_pages": self.list_pages,
            "list_ids": self.list_ids,
            "detail_success": self.detail_success,
            "detail_failed": self.detail_failed,
            "detail_not_found": self.detail_not_found,
            "proxy_switched": self.proxy_switched,
            "block_count": self.block_count,
            "rate_limit_count": self.rate_limit_count,
            "error_403_count": self.error_403_count,
            "elapsed_seconds": int(elapsed),
            "elapsed_minutes": round(elapsed / 60, 1),
            "success_rate": f"{self.detail_success / max(1, self.list_ids) * 100:.1f}%",
        }


class JobKoreaScraperV2:
    """잡코리아 크롤러 V2 Lite - AJAX 기반"""

    def __init__(
        self,
        num_workers: int = 10,
        use_proxy: bool = False,
        fallback_to_proxy: bool = True,
        proxy_pool_size: int = 10,
        proxy_speed_threshold: float = 3.0,
        proxy_delay_threshold: float = 0.3,
        proxy_speed_consecutive: int = 2,
        proxy_speed_warmup: int = 200,
        proxy_start_pool: bool = False,
        proxy_pool_warmup: bool = True,
        proxy_worker_rotate_threshold: int = 2,
        proxy_session_lifetime: str = "10m",
    ):
        """
        Args:
            num_workers: 병렬 워커 수 (기본 10)
            use_proxy: 처음부터 프록시 사용 (기본 False)
            fallback_to_proxy: 차단 시 프록시로 폴백 (기본 True)
            proxy_pool_size: 풀 프록시 워커 수 (기본 10)
            proxy_speed_threshold: 풀 전환 속도 임계값 (기본 3.0건/s)
            proxy_delay_threshold: 레이트리밋 딜레이 임계값 (기본 0.3s)
            proxy_speed_consecutive: 연속 조건 만족 횟수 (기본 2회)
            proxy_speed_warmup: 전환 판단 시작 건수 (기본 200건)
            proxy_start_pool: 시작 시 풀 모드 사용 여부 (기본 False)
            proxy_pool_warmup: 풀 워커 쿠키 워밍업 여부 (기본 True)
            proxy_worker_rotate_threshold: 풀 워커 세션 교체 임계값 (기본 2)
            proxy_session_lifetime: Sticky 세션 유지 시간 (기본 10분)
        """
        self.num_workers = num_workers
        self.use_proxy = use_proxy
        self.fallback_to_proxy = fallback_to_proxy
        self.proxy_pool_size = proxy_pool_size
        self.proxy_speed_threshold = proxy_speed_threshold
        self.proxy_delay_threshold = proxy_delay_threshold
        self.proxy_speed_consecutive = proxy_speed_consecutive
        self.proxy_speed_warmup = proxy_speed_warmup
        self.proxy_start_pool = proxy_start_pool
        self.proxy_pool_warmup = proxy_pool_warmup
        self.proxy_worker_rotate_threshold = proxy_worker_rotate_threshold
        self.proxy_session_lifetime = proxy_session_lifetime

        self.session_manager = SessionManager(use_proxy=use_proxy)
        self.proxy_session: Optional[ProxySessionManager] = None
        self.stats = CrawlerStats()
        self.rate_limiter = AdaptiveRateLimiter()

        # 워커 클라이언트 풀
        self.clients: List[httpx.AsyncClient] = []

        # 파서 및 유틸리티
        self.parser = DetailPageParser()
        self.dedup_generator = DedupKeyGenerator()

        # 상태
        self.total_count = 0
        self.total_pages = 0
        if use_proxy:
            self.proxy_mode = "pool" if proxy_start_pool else "single"
        else:
            self.proxy_mode = "none"
        self.proxy_enabled = self.proxy_mode != "none"
        self.block_count = 0
        self._slow_speed_count = 0
        self.proxy_worker_failures: List[int] = []
        self.proxy_worker_sessions: List[str] = []

    async def initialize(self):
        """크롤러 초기화"""
        logger.info("V2 크롤러 초기화 시작")

        # 메인 세션 초기화
        client = await self.session_manager.initialize()
        cookies = self.session_manager.get_cookies()

        # 전체 공고 수 확인
        ajax = AjaxClient(client)
        self.total_count = await ajax.get_total_count()
        self.total_pages = (self.total_count // CrawlerConfig.JOBS_PER_PAGE) + 1

        logger.info(f"서울 전체 공고: {self.total_count:,}건, {self.total_pages:,}페이지")

        # 워커 클라이언트 풀 생성
        await self._create_worker_pool(cookies)

        logger.info(f"초기화 완료: {self.num_workers}개 워커, 프록시 {'ON' if self.use_proxy else 'OFF'}")

    def _copy_cookies(self, cookies: Optional[httpx.Cookies]) -> httpx.Cookies:
        new_cookies = httpx.Cookies()
        if cookies:
            new_cookies.update(cookies)
        return new_cookies

    def _make_proxy_session_id(self, worker_idx: int) -> str:
        """8자 세션 ID 생성 (IPRoyal 권장 규칙)"""
        suffix = random.randint(0, 99999)
        return f"w{worker_idx:02d}{suffix:05d}"

    async def _fetch_proxy_cookies(self, proxy_url: str, worker_idx: int) -> httpx.Cookies:
        """프록시 경유로 세션 쿠키 워밍업"""
        client = httpx.AsyncClient(
            timeout=CrawlerConfig.DEFAULT_TIMEOUT,
            headers={
                "User-Agent": USER_AGENTS[worker_idx % len(USER_AGENTS)],
                **CrawlerConfig.DEFAULT_HEADERS,
            },
            follow_redirects=True,
            proxy=proxy_url,
        )
        try:
            resp = await client.get(
                CrawlerConfig.get_joblist_url(),
                params={"menucode": "local", "local": CrawlerConfig.SEOUL_LOCAL_CODE},
            )
            if resp.status_code != 200:
                logger.warning("프록시 쿠키 워밍업 실패: 워커 %d, 상태 %s", worker_idx, resp.status_code)
        finally:
            cookies = self._copy_cookies(client.cookies)
            await client.aclose()
        return cookies

    async def _create_worker_pool(self, cookies: httpx.Cookies):
        """워커 클라이언트 풀 생성"""
        # 기존 클라이언트 정리
        for client in self.clients:
            await client.aclose()
        self.clients = []

        proxy_mode = self.proxy_mode
        if proxy_mode != "none" and not self.session_manager._proxy_configured():
            logger.warning("프록시 설정 누락: PROXY_* 환경변수 확인 필요")
            proxy_mode = "none"
            self.proxy_mode = "none"
            self.proxy_enabled = False
        self.proxy_worker_failures = [0] * self.num_workers
        self.proxy_worker_sessions = []
        worker_cookies: List[httpx.Cookies] = []

        if proxy_mode == "pool":
            self.proxy_worker_sessions = [
                self._make_proxy_session_id(i) for i in range(self.num_workers)
            ]

            if self.proxy_pool_warmup:
                # 병렬 워밍업으로 30초 → 5초 단축
                async def warmup_worker(idx: int, session_id: str) -> httpx.Cookies:
                    proxy_url = self._build_proxy_url(session_id)
                    if not proxy_url:
                        return self._copy_cookies(cookies)
                    try:
                        return await self._fetch_proxy_cookies(proxy_url, idx)
                    except Exception as e:
                        logger.warning("워커 %d 쿠키 워밍업 실패: %s", idx, e)
                        return self._copy_cookies(cookies)

                warmup_tasks = [
                    warmup_worker(i, session_id)
                    for i, session_id in enumerate(self.proxy_worker_sessions)
                ]
                worker_cookies = await asyncio.gather(*warmup_tasks)
                worker_cookies = list(worker_cookies)  # tuple → list
                logger.info("프록시 풀 워밍업 완료: %d개 워커 병렬 처리", len(worker_cookies))
            else:
                worker_cookies = [self._copy_cookies(cookies) for _ in range(self.num_workers)]

        for i in range(self.num_workers):
            proxy_url = None
            client_cookies = cookies
            if proxy_mode == "single":
                proxy_url = self._build_proxy_url("single")
            elif proxy_mode == "pool":
                proxy_url = self._build_proxy_url(self.proxy_worker_sessions[i])
                if worker_cookies:
                    client_cookies = worker_cookies[i]
            client = httpx.AsyncClient(
                timeout=CrawlerConfig.DEFAULT_TIMEOUT,
                headers={
                    "User-Agent": USER_AGENTS[i % len(USER_AGENTS)],
                    **CrawlerConfig.DEFAULT_HEADERS,
                },
                cookies=client_cookies,
                follow_redirects=True,
                proxy=proxy_url,
            )
            self.clients.append(client)

    def _build_proxy_url(self, session_id: Optional[str] = None) -> Optional[str]:
        """프록시 URL 생성 (세션 고정 옵션 포함)"""
        if not self.session_manager._proxy_configured():
            return None

        if session_id:
            return (
                f"http://{SessionManager.PROXY_USERNAME}:{SessionManager.PROXY_PASSWORD}"
                f"_session-{session_id}_lifetime-{self.proxy_session_lifetime}"
                f"@{SessionManager.PROXY_HOST}:{SessionManager.PROXY_PORT}"
            )
        return (
            f"http://{SessionManager.PROXY_USERNAME}:{SessionManager.PROXY_PASSWORD}"
            f"@{SessionManager.PROXY_HOST}:{SessionManager.PROXY_PORT}"
        )

    async def _rotate_proxy_worker(self, worker_idx: int, reason: str):
        """풀 모드에서 워커 프록시 세션 교체"""
        if self.proxy_mode != "pool":
            return
        if worker_idx >= len(self.clients):
            return

        session_id = self._make_proxy_session_id(worker_idx)
        proxy_url = self._build_proxy_url(session_id)
        if not proxy_url:
            logger.warning("워커 %d 프록시 교체 실패: 프록시 설정 누락", worker_idx)
            return

        cookies = None
        if self.proxy_pool_warmup:
            try:
                cookies = await self._fetch_proxy_cookies(proxy_url, worker_idx)
            except Exception as e:
                logger.warning("워커 %d 쿠키 워밍업 실패: %s", worker_idx, e)

        if cookies is None:
            cookies = self._copy_cookies(self.session_manager.get_cookies())

        client = httpx.AsyncClient(
            timeout=CrawlerConfig.DEFAULT_TIMEOUT,
            headers={
                "User-Agent": USER_AGENTS[worker_idx % len(USER_AGENTS)],
                **CrawlerConfig.DEFAULT_HEADERS,
            },
            cookies=cookies,
            follow_redirects=True,
            proxy=proxy_url,
        )

        old_client = self.clients[worker_idx]
        self.clients[worker_idx] = client
        await old_client.aclose()

        if worker_idx < len(self.proxy_worker_sessions):
            self.proxy_worker_sessions[worker_idx] = session_id
        if worker_idx < len(self.proxy_worker_failures):
            self.proxy_worker_failures[worker_idx] = 0

        logger.info("워커 %d 프록시 세션 교체 완료 (%s)", worker_idx, reason)

    async def _handle_proxy_worker_failure(self, worker_idx: int, reason: str):
        """풀 모드 워커 실패 누적 처리"""
        if self.proxy_mode != "pool":
            return
        if worker_idx >= len(self.proxy_worker_failures):
            return

        self.proxy_worker_failures[worker_idx] += 1
        if self.proxy_worker_failures[worker_idx] >= self.proxy_worker_rotate_threshold:
            await self._rotate_proxy_worker(worker_idx, reason)

    async def _switch_to_proxy(self):
        """프록시 모드로 전환"""
        await self._switch_to_proxy_pool("차단 감지")

    async def _switch_to_proxy_pool(self, reason: str):
        """풀 프록시 모드로 전환"""
        if self.proxy_mode == "pool":
            return

        if not self.session_manager._proxy_configured():
            logger.warning("프록시 설정 누락으로 전환 생략")
            self.proxy_mode = "none"
            self.proxy_enabled = False
            return

        logger.warning("%s: 프록시 풀(%d) 모드로 전환 중...", reason, self.proxy_pool_size)
        self.proxy_mode = "pool"
        self.proxy_enabled = True
        self.stats.proxy_switched = True

        if self.proxy_pool_size > 0:
            self.num_workers = self.proxy_pool_size

        cookies = self.session_manager.get_cookies()
        await self._create_worker_pool(cookies)

        self.rate_limiter.reset()
        self.block_count = 0
        self._slow_speed_count = 0
        logger.info("프록시 풀 모드 전환 완료")

    async def _maybe_switch_to_proxy_pool(self, window_speed: float, processed: int):
        """속도/레이트리밋 기준으로 풀 프록시 전환 판단"""
        if self.proxy_mode != "single":
            return
        if self.proxy_pool_size <= 1:
            return
        if processed < self.proxy_speed_warmup:
            return
        if window_speed <= 0:
            return

        rate_limited = (
            self.rate_limiter.get_delay() >= self.proxy_delay_threshold
            or self.rate_limiter.is_blocked()
            or self.block_count >= 1
        )

        if window_speed < self.proxy_speed_threshold and rate_limited:
            self._slow_speed_count += 1
        else:
            self._slow_speed_count = 0

        if self._slow_speed_count >= self.proxy_speed_consecutive:
            await self._switch_to_proxy_pool(f"속도 저하 {window_speed:.1f}건/s")

    # ========== 목록 수집 ==========

    async def crawl_list(
        self,
        max_pages: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> Set[str]:
        """
        목록 크롤링 - Job ID 수집

        Args:
            max_pages: 최대 페이지 수 (None이면 전체)
            progress_callback: 진행 콜백 (current, total)

        Returns:
            Set[str]: 수집된 Job ID 세트
        """
        self.stats.start_time = datetime.now()
        pages = min(self.total_pages, max_pages or self.total_pages)

        logger.info(f"목록 수집 시작: {pages}페이지")
        print(f"[V2] 목록 수집 시작: {pages}페이지", flush=True)

        collected_ids: Set[str] = set()
        page_queue: asyncio.Queue = asyncio.Queue()

        for p in range(1, pages + 1):
            await page_queue.put(p)

        async def list_worker(worker_id: int):
            client = self.clients[worker_id]
            ajax = AjaxClient(client)
            local_count = 0

            while True:
                try:
                    page = page_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                try:
                    ids = await ajax.fetch_page(page)
                    collected_ids.update(ids)
                    local_count += len(ids)
                    self.stats.list_pages += 1
                    self.stats.list_ids += len(ids)

                    if page % 50 == 0 or page <= 5:
                        print(f"[W{worker_id}] 페이지 {page}: {len(ids)}개 (누적 {len(collected_ids)})", flush=True)

                    if progress_callback:
                        await progress_callback(page, pages)

                    await asyncio.sleep(self.rate_limiter.get_delay())

                except Exception as e:
                    logger.warning(f"Worker {worker_id} 페이지 {page} 실패: {e}")
                    await asyncio.sleep(0.5)

        workers = [list_worker(i) for i in range(self.num_workers)]
        await asyncio.gather(*workers)

        logger.info(f"목록 수집 완료: {len(collected_ids):,}개 ID")
        print(f"[V2] 목록 수집 완료: {len(collected_ids):,}개 ID", flush=True)

        return collected_ids

    # ========== 상세 수집 ==========

    async def crawl_details(
        self,
        job_ids: Set[str],
        save_callback: Optional[Callable[[List[Dict]], Awaitable[dict]]] = None,
        batch_size: int = 500,
        parallel_batch: int = 10,
        retry_limit: int = 2,
        retry_backoff: float = 1.5,
        min_parallel_batch: int = 3,
    ) -> Tuple[int, Dict]:
        """
        상세 페이지 크롤링

        Args:
            job_ids: 수집할 Job ID 세트
            save_callback: 저장 콜백
            batch_size: 저장 배치 크기
            parallel_batch: 동시 워커 수
            retry_limit: 실패 재시도 횟수 (기본 2)
            retry_backoff: 재시도 라운드 딜레이 배수 (기본 1.5)
            min_parallel_batch: 재시도 시 최소 동시 요청 수 (기본 3)

        Returns:
            (성공 건수, 저장 통계)
        """
        orchestrator = DetailCrawlOrchestrator(
            scraper=self,
            batch_size=batch_size,
            parallel_batch=parallel_batch,
            retry_limit=retry_limit,
            retry_backoff=retry_backoff,
            min_parallel_batch=min_parallel_batch,
        )
        return await orchestrator.run(job_ids, save_callback)

    async def _fetch_detail_with_fallback(self, job_id: str, worker_idx: int) -> Optional[Dict]:
        """적응형 폴백으로 상세 정보 수집"""
        client = self.clients[worker_idx]

        try:
            result = await self._fetch_detail_info(client, job_id)
            if result:
                self.rate_limiter.on_success()
                self.block_count = 0
                if self.proxy_mode == "pool" and worker_idx < len(self.proxy_worker_failures):
                    self.proxy_worker_failures[worker_idx] = 0
                return result

        except BlockedError as e:
            self.block_count += 1
            self.stats.block_count += 1
            self.rate_limiter.on_error(429)
            logger.warning("차단 감지 (%s): %s (누적 %d회)", job_id, e, self.stats.block_count)

            if self.proxy_mode == "pool":
                await self._handle_proxy_worker_failure(worker_idx, "차단 감지")

            if self.block_count >= 5 and self.fallback_to_proxy and self.proxy_mode != "pool":
                await self._switch_to_proxy()
                client = self.clients[worker_idx]
                return await self._fetch_detail_info(client, job_id)

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response else None
            # 404: 삭제된 공고 - 재시도 없이 스킵
            if status_code == 404:
                return {"_not_found": True}
            elif status_code in [403, 429]:
                self.block_count += 1
                self.rate_limiter.on_error(status_code)
                # 통계 기록
                if status_code == 429:
                    self.stats.rate_limit_count += 1
                    logger.warning("레이트리밋 429 (%s) - 누적 %d회", job_id, self.stats.rate_limit_count)
                elif status_code == 403:
                    self.stats.error_403_count += 1
                    logger.warning("접근거부 403 (%s) - 누적 %d회", job_id, self.stats.error_403_count)

                if self.proxy_mode == "pool":
                    await self._handle_proxy_worker_failure(worker_idx, f"HTTP {status_code}")

                # 차단 감지 → 프록시 전환
                if self.block_count >= 5 and self.fallback_to_proxy and self.proxy_mode != "pool":
                    await self._switch_to_proxy()
                    # 프록시로 재시도
                    client = self.clients[worker_idx]
                    return await self._fetch_detail_info(client, job_id)
            else:
                logger.debug("상세 수집 실패 (%s): HTTP %s", job_id, status_code)

        except httpx.TransportError as e:
            if self.proxy_mode == "pool":
                await self._handle_proxy_worker_failure(worker_idx, type(e).__name__)
            logger.debug(
                "상세 수집 네트워크 실패 (%s): %s %s",
                job_id,
                type(e).__name__,
                e,
            )

        except Exception as e:
            logger.debug(
                "상세 수집 실패 (%s): %s %s",
                job_id,
                type(e).__name__,
                e,
            )

        return None

    async def _fetch_detail_info(self, client: httpx.AsyncClient, job_id: str) -> Optional[Dict]:
        """상세 페이지에서 정보 추출"""
        try:
            url = CrawlerConfig.get_detail_url(job_id)
            response = await client.get(url, timeout=CrawlerConfig.DETAIL_TIMEOUT)
            response.raise_for_status()

            html = response.text

            # 차단 감지
            if self._detect_blocking(response):
                raise BlockedError("차단 감지")

            # 파싱
            try:
                return self.parser.parse(job_id, html)
            except Exception as e:
                logger.debug(
                    "상세 파싱 실패 (%s): %s %s (len=%s)",
                    job_id,
                    type(e).__name__,
                    e,
                    len(html),
                )
                return None

        except httpx.HTTPStatusError:
            raise
        except BlockedError:
            raise
        except Exception as e:
            logger.debug(
                "상세 수집 실패 (%s): %s %s",
                job_id,
                type(e).__name__,
                e,
            )
            return None

    def _detect_blocking(self, response: httpx.Response) -> bool:
        """차단/캡차 감지"""
        if response.status_code in [403, 429]:
            return True
        text = response.text.lower()
        if "captcha" in text or "보안문자" in text:
            return True
        if "비정상적인" in text or "접근이 차단" in text:
            return True
        return False

    # ========== 전체 크롤링 ==========

    async def crawl_all(
        self,
        max_pages: Optional[int] = None,
        save_callback: Optional[Callable[[List[Dict]], Awaitable[dict]]] = None,
        save_batch_size: int = 500,
        skip_existing: bool = False,
        existing_ids: Optional[Set[str]] = None,
    ) -> Tuple[int, Set[str], Dict]:
        """
        전체 크롤링 (목록 + 상세)

        Args:
            max_pages: 최대 페이지 수
            save_callback: 저장 콜백
            save_batch_size: 저장 배치 크기
            skip_existing: True면 이미 DB에 있는 공고 상세 크롤링 스킵
            existing_ids: 기존 공고 ID 세트 (skip_existing=True일 때 사용)
                          None이면 자동으로 DB에서 조회

        Returns:
            (수집 건수, ID 세트, 저장 통계)
        """
        self.stats.start_time = datetime.now()

        print("=" * 60, flush=True)
        print("[V2] 전체 크롤링 시작", flush=True)
        print(f"  - 워커: {self.num_workers}개", flush=True)
        print(f"  - 프록시: {'ON' if self.use_proxy else 'OFF (폴백 활성화)'}", flush=True)
        print(f"  - 기존 공고 스킵: {'ON' if skip_existing else 'OFF'}", flush=True)
        print("=" * 60, flush=True)

        # 1. 목록 수집
        job_ids = await self.crawl_list(max_pages)

        if not job_ids:
            logger.warning("수집된 ID 없음")
            return 0, set(), {}

        # 2. 기존 공고 스킵 처리
        new_ids = job_ids
        skipped_count = 0

        if skip_existing:
            if existing_ids is None:
                # DB에서 기존 ID 조회
                from app.db.firestore import get_existing_job_ids
                print("[V2] DB에서 기존 공고 ID 조회 중...", flush=True)
                existing_ids = await get_existing_job_ids()
                print(f"[V2] 기존 공고: {len(existing_ids):,}건", flush=True)

            # 새 공고만 필터링
            new_ids = job_ids - existing_ids
            skipped_count = len(job_ids) - len(new_ids)

            print(f"[V2] 목록에서 수집: {len(job_ids):,}건", flush=True)
            print(f"[V2] 기존 공고 스킵: {skipped_count:,}건", flush=True)
            print(f"[V2] 새 공고 크롤링: {len(new_ids):,}건", flush=True)

            if not new_ids:
                print("[V2] 새 공고 없음 - 크롤링 종료", flush=True)
                return 0, job_ids, {"new": 0, "updated": 0, "failed": 0, "skipped": skipped_count}

        # 3. 상세 수집 (새 공고만)
        success_count, save_stats = await self.crawl_details(
            new_ids,
            save_callback=save_callback,
            batch_size=save_batch_size,
        )

        # 스킵 카운트 추가
        save_stats["skipped"] = skipped_count

        # 결과 출력
        print("=" * 60, flush=True)
        print("[V2] 크롤링 완료", flush=True)
        stats = self.stats.summary()
        for k, v in stats.items():
            print(f"  - {k}: {v}", flush=True)
        if skipped_count > 0:
            print(f"  - skipped: {skipped_count}", flush=True)
        print("=" * 60, flush=True)

        return success_count, job_ids, save_stats

    async def close(self):
        """리소스 정리"""
        await self.session_manager.close()
        for client in self.clients:
            await client.aclose()
        self.clients = []
