"""
잡코리아 크롤러 V2 Lite
- AJAX 엔드포인트 사용으로 페이지네이션 정상 작동
- 적응형 폴백: 프록시 없이 시작 → 차단 시 프록시 전환
"""

import asyncio
import random
import re
import time
from datetime import datetime
from typing import Optional, List, Dict, Set, Tuple, Callable, Awaitable

import httpx
from bs4 import BeautifulSoup

from app.config import settings, USER_AGENTS
from app.core.session_manager import SessionManager, ProxySessionManager
from app.core.ajax_client import AjaxClient, AdaptiveRateLimiter, BlockedError
from app.normalizers import normalize_job_type, get_job_category, get_mvp_category, normalize_location, parse_salary
from app.normalizers.company import CompanyNormalizer
from app.normalizers.dedup import DedupKeyGenerator
from app.logging_config import get_logger

logger = get_logger("crawler.v2")


class CrawlerStats:
    """크롤링 통계"""

    def __init__(self):
        self.list_pages = 0
        self.list_ids = 0
        self.detail_success = 0
        self.detail_failed = 0
        self.proxy_switched = False
        self.start_time = None
        self.errors = []

    def summary(self) -> dict:
        elapsed = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        return {
            "list_pages": self.list_pages,
            "list_ids": self.list_ids,
            "detail_success": self.detail_success,
            "detail_failed": self.detail_failed,
            "proxy_switched": self.proxy_switched,
            "elapsed_seconds": int(elapsed),
            "elapsed_minutes": round(elapsed / 60, 1),
            "success_rate": f"{self.detail_success / max(1, self.list_ids) * 100:.1f}%",
        }


class JobKoreaScraperV2:
    """잡코리아 크롤러 V2 Lite - AJAX 기반"""

    BASE_URL = "https://www.jobkorea.co.kr"
    DETAIL_URL = f"{BASE_URL}/Recruit/GI_Read"
    JOBS_PER_PAGE = 40

    def __init__(
        self,
        num_workers: int = 10,
        use_proxy: bool = False,
        fallback_to_proxy: bool = True,
    ):
        """
        Args:
            num_workers: 병렬 워커 수 (기본 10)
            use_proxy: 처음부터 프록시 사용 (기본 False)
            fallback_to_proxy: 차단 시 프록시로 폴백 (기본 True)
        """
        self.num_workers = num_workers
        self.use_proxy = use_proxy
        self.fallback_to_proxy = fallback_to_proxy

        self.session_manager = SessionManager(use_proxy=use_proxy)
        self.proxy_session: Optional[ProxySessionManager] = None
        self.stats = CrawlerStats()
        self.rate_limiter = AdaptiveRateLimiter()

        # 워커 클라이언트 풀
        self.clients: List[httpx.AsyncClient] = []

        # Normalizers
        self.company_normalizer = CompanyNormalizer()
        self.dedup_generator = DedupKeyGenerator()

        # 상태
        self.total_count = 0
        self.total_pages = 0
        self.proxy_enabled = False
        self.block_count = 0

    async def initialize(self):
        """크롤러 초기화"""
        logger.info("V2 크롤러 초기화 시작")

        # 메인 세션 초기화
        client = await self.session_manager.initialize()
        cookies = self.session_manager.get_cookies()

        # 전체 공고 수 확인
        ajax = AjaxClient(client)
        self.total_count = await ajax.get_total_count()
        self.total_pages = (self.total_count // self.JOBS_PER_PAGE) + 1

        logger.info(f"서울 전체 공고: {self.total_count:,}건, {self.total_pages:,}페이지")

        # 워커 클라이언트 풀 생성
        await self._create_worker_pool(cookies)

        logger.info(f"초기화 완료: {self.num_workers}개 워커, 프록시 {'ON' if self.use_proxy else 'OFF'}")

    async def _create_worker_pool(self, cookies: httpx.Cookies):
        """워커 클라이언트 풀 생성"""
        # 기존 클라이언트 정리
        for client in self.clients:
            await client.aclose()
        self.clients = []

        proxy_url = None
        if self.proxy_enabled or self.use_proxy:
            proxy_url = f"http://{SessionManager.PROXY_USERNAME}:{SessionManager.PROXY_PASSWORD}@{SessionManager.PROXY_HOST}:{SessionManager.PROXY_PORT}"

        for i in range(self.num_workers):
            client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": USER_AGENTS[i % len(USER_AGENTS)],
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "ko-KR,ko;q=0.9",
                },
                cookies=cookies,
                follow_redirects=True,
                proxy=proxy_url,
            )
            self.clients.append(client)

    async def _switch_to_proxy(self):
        """프록시 모드로 전환"""
        if self.proxy_enabled:
            return

        logger.warning("차단 감지! 프록시 모드로 전환 중...")
        self.proxy_enabled = True
        self.stats.proxy_switched = True

        cookies = self.session_manager.get_cookies()
        await self._create_worker_pool(cookies)

        self.rate_limiter.reset()
        logger.info("프록시 모드 전환 완료")

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
    ) -> Tuple[int, Dict]:
        """
        상세 페이지 크롤링

        Args:
            job_ids: 수집할 Job ID 세트
            save_callback: 저장 콜백
            batch_size: 저장 배치 크기
            parallel_batch: 동시 요청 수

        Returns:
            (성공 건수, 저장 통계)
        """
        logger.info(f"상세 수집 시작: {len(job_ids):,}건")
        print(f"[V2] 상세 수집 시작: {len(job_ids):,}건", flush=True)

        id_list = list(job_ids)
        total_saved = {"new": 0, "updated": 0, "failed": 0}
        pending_jobs: List[Dict] = []

        # 진행 상황
        processed = 0
        start_time = time.time()

        for batch_start in range(0, len(id_list), parallel_batch):
            batch_ids = id_list[batch_start:batch_start + parallel_batch]

            # 병렬로 상세 페이지 수집
            tasks = [
                self._fetch_detail_with_fallback(job_id, i % self.num_workers)
                for i, job_id in enumerate(batch_ids)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, dict) and result:
                    pending_jobs.append(result)
                    self.stats.detail_success += 1
                else:
                    self.stats.detail_failed += 1

            processed += len(batch_ids)

            # 진행 상황 출력
            if processed % 100 == 0 or processed == len(id_list):
                elapsed = time.time() - start_time
                speed = processed / elapsed if elapsed > 0 else 0
                eta = (len(id_list) - processed) / speed if speed > 0 else 0
                print(f"[V2] 진행: {processed}/{len(id_list)} ({speed:.1f}건/s, ETA: {eta/60:.1f}분)", flush=True)

            # 배치 저장
            if len(pending_jobs) >= batch_size and save_callback:
                try:
                    result = await save_callback(pending_jobs)
                    total_saved["new"] += result.get("new", 0)
                    total_saved["updated"] += result.get("updated", 0)
                    print(f"[V2] 저장: {len(pending_jobs)}건", flush=True)
                    pending_jobs = []
                except Exception as e:
                    logger.error(f"저장 실패: {e}")

            # 속도 조절
            await asyncio.sleep(self.rate_limiter.get_delay())

        # 남은 데이터 저장
        if pending_jobs and save_callback:
            try:
                result = await save_callback(pending_jobs)
                total_saved["new"] += result.get("new", 0)
                total_saved["updated"] += result.get("updated", 0)
                print(f"[V2] 최종 저장: {len(pending_jobs)}건", flush=True)
            except Exception as e:
                logger.error(f"최종 저장 실패: {e}")

        logger.info(f"상세 수집 완료: 성공 {self.stats.detail_success}, 실패 {self.stats.detail_failed}")
        return self.stats.detail_success, total_saved

    async def _fetch_detail_with_fallback(self, job_id: str, worker_idx: int) -> Optional[Dict]:
        """적응형 폴백으로 상세 정보 수집"""
        client = self.clients[worker_idx]

        try:
            result = await self._fetch_detail_info(client, job_id)
            if result:
                self.rate_limiter.on_success()
                self.block_count = 0
                return result

        except httpx.HTTPStatusError as e:
            if e.response.status_code in [403, 429]:
                self.block_count += 1
                self.rate_limiter.on_error(e.response.status_code)

                # 차단 감지 → 프록시 전환
                if self.block_count >= 5 and self.fallback_to_proxy and not self.proxy_enabled:
                    await self._switch_to_proxy()
                    # 프록시로 재시도
                    client = self.clients[worker_idx]
                    return await self._fetch_detail_info(client, job_id)

        except Exception as e:
            logger.debug(f"상세 수집 실패 ({job_id}): {e}")

        return None

    async def _fetch_detail_info(self, client: httpx.AsyncClient, job_id: str) -> Optional[Dict]:
        """상세 페이지에서 정보 추출"""
        try:
            url = f"{self.DETAIL_URL}/{job_id}"
            response = await client.get(url, timeout=15.0)
            response.raise_for_status()

            html = response.text

            # 차단 감지
            if self._detect_blocking(response):
                raise BlockedError("차단 감지")

            # 파싱
            return self._parse_detail_page(job_id, html)

        except httpx.HTTPStatusError:
            raise
        except Exception as e:
            logger.debug(f"상세 파싱 실패 ({job_id}): {e}")
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

    def _parse_detail_page(self, job_id: str, html: str) -> Dict:
        """상세 페이지 파싱"""
        soup = BeautifulSoup(html, "lxml")

        # 제목 - 여러 소스에서 추출 시도
        title = ""
        # 1. JSON-LD의 title 필드 (가장 정확함)
        json_ld_title = re.search(r'"@type"\s*:\s*"JobPosting"[^}]*"title"\s*:\s*"([^"]+)"', html, re.DOTALL)
        if not json_ld_title:
            json_ld_title = re.search(r'"title"\s*:\s*"([^"]{10,})"', html)  # 10자 이상
        if json_ld_title:
            title = json_ld_title.group(1)
        # 2. CSS 셀렉터
        if not title:
            title_el = soup.select_one("h1.title, .tit_job, .job-title, .recruit-title")
            if title_el:
                title = title_el.get_text(strip=True)
        # 3. og:title 메타태그
        if not title:
            og_title = soup.select_one('meta[property="og:title"]')
            if og_title:
                title = og_title.get("content", "")
        # 4. <title> 태그 (최후 수단, "회사명 채용" 패턴 필터링)
        if not title:
            title_match = re.search(r'<title>([^<]+)</title>', html)
            if title_match:
                raw_title = title_match.group(1).split(" - ")[0].split(" | ")[0].strip()
                # "XXX 채용" 패턴이면 스킵 (잘못된 title)
                if not re.match(r'^.{2,20}\s*채용$', raw_title):
                    title = raw_title

        # 회사명 - JSON-LD에서 먼저 추출 시도
        company_name = ""
        # 1. JSON-LD hiringOrganization.name에서 추출 (가장 정확함)
        hiring_org_match = re.search(r'"hiringOrganization"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', html)
        if hiring_org_match:
            company_name = hiring_org_match.group(1)
        # 2. CSS selector 폴백
        if not company_name:
            company_el = soup.select_one(".company-name, .coname, .co_name a")
            if company_el:
                company_name = company_el.get_text(strip=True)

        # workFields 추출
        work_fields_match = re.search(r'workFields\\\\?":\[([^\]]*)\]', html)
        work_fields = []
        if work_fields_match:
            content = work_fields_match.group(1)
            work_fields = re.findall(r'"([^"]+)"', content)

        # 급여 정보
        salary_text = ""
        salary_patterns = [
            r'(월급?\s*[\d,]+\s*~\s*[\d,]+\s*만원)',
            r'(연봉?\s*[\d,]+\s*~\s*[\d,]+\s*만원)',
            r'([\d,]+\s*~\s*[\d,]+\s*만원)',
            r'(월급?\s*[\d,]+\s*만원)',
            r'(연봉?\s*[\d,]+\s*만원)',
            r'salaryName["\s:]+([^"]+)"',
        ]
        for pattern in salary_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                extracted = match.group(1).strip()
                extracted = re.sub(r'<[^>]+>', '', extracted)
                if len(extracted) < 30:
                    salary_text = extracted
                    break

        salary_data = parse_salary(salary_text)

        # 회사 주소
        company_address = ""
        json_ld_match = re.search(r'"addressLocality"\s*:\s*"([^"]+)"', html)
        if json_ld_match:
            company_address = json_ld_match.group(1).strip()

        # 기업규모
        company_size = ""
        size_match = re.search(
            r'(중소기업|중견기업|대기업|대기업\(계열사\)|스타트업|외국계|공기업|공공기관)',
            html
        )
        if size_match:
            company_size = size_match.group(1)

        # 정규화
        primary_job_type = work_fields[0] if work_fields else ""
        normalized = normalize_job_type(primary_job_type) if primary_job_type else ""
        category = get_job_category(normalized) if normalized else "기타"
        mvp_category = get_mvp_category(category)
        location_info = normalize_location(company_address) if company_address else {}

        # 회사명 정규화
        company_name_normalized, company_type = self.company_normalizer.normalize(company_name)

        # 마감일 추출
        deadline_info = self._extract_deadline_info(html)

        now = datetime.now()

        return {
            "id": f"jk_{job_id}",
            "source": "jobkorea",
            "company_name_raw": company_name,
            "company_name": company_name_normalized,
            "company_type": company_type,
            "title": title,
            "url": f"{self.DETAIL_URL}/{job_id}",
            "job_type": normalized or primary_job_type,
            "job_type_raw": ", ".join(work_fields[:3]),
            "job_category": category,
            "mvp_category": mvp_category,
            "job_keywords": work_fields[:5],
            "location_sido": location_info.get("sido", "서울"),
            "location_gugun": location_info.get("gugun", ""),
            "location_dong": location_info.get("dong", ""),
            "location_full": company_address or location_info.get("full", ""),
            "company_address": company_address,
            "salary_text": salary_data["text"],
            "salary_min": salary_data["min"],
            "salary_max": salary_data["max"],
            "salary_type": salary_data["type"],
            "company_size": company_size,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            "dedup_key": "",  # 나중에 계산
            **deadline_info,  # deadline, deadline_type, deadline_date
        }

    def _extract_deadline_info(self, html: str) -> Dict:
        """마감일 정보 추출"""
        from datetime import datetime as dt

        result = {
            "deadline": "",
            "deadline_type": "unknown",
            "deadline_date": None,
        }

        # 1. 날짜 패턴 먼저 시도 (우선순위 높음)
        date_patterns = [
            # Meta description: 마감일 : 2025.04.11
            (r'마감일\s*:\s*(\d{4}\.\d{2}\.\d{2})', "date_dot"),
            # JSON-LD validThrough (한국식)
            (r'"validThrough"\s*:\s*"?(\d{4}\.\d{2}\.\d{2})"?', "date_dot"),
            # JSON-LD validThrough (ISO)
            (r'"validThrough"\s*:\s*"([^"]+)"', "date_iso"),
            # applicationEndAt
            (r'"applicationEndAt"\s*:\s*"([^"]+)"', "date_iso"),
        ]

        for pattern, dtype in date_patterns:
            match = re.search(pattern, html)
            if match:
                date_str = match.group(1).strip()
                try:
                    if dtype == "date_dot":
                        # 2025.04.11 형식
                        parsed = dt.strptime(date_str, "%Y.%m.%d")
                        result["deadline"] = parsed.strftime("%m.%d")
                        result["deadline_date"] = parsed
                        result["deadline_type"] = "date"
                        return result
                    elif dtype == "date_iso":
                        if "T" in date_str:
                            parsed = dt.fromisoformat(date_str.replace("Z", "+00:00").split("+")[0])
                        elif "-" in date_str:
                            parsed = dt.strptime(date_str[:10], "%Y-%m-%d")
                        else:
                            continue
                        result["deadline"] = parsed.strftime("%m.%d")
                        result["deadline_date"] = parsed
                        result["deadline_type"] = "date"
                        return result
                except:
                    pass

        # 2. 상시채용/채용시마감 패턴
        ongoing_patterns = [
            (r'상시\s*채용|상시채용', "ongoing"),
            (r'채용\s*시\s*마감|채용시까지', "until_hired"),
        ]

        for pattern, dtype in ongoing_patterns:
            if re.search(pattern, html, re.IGNORECASE):
                if dtype == "ongoing":
                    result["deadline"] = "상시채용"
                    result["deadline_type"] = "ongoing"
                else:
                    result["deadline"] = "채용시 마감"
                    result["deadline_type"] = "until_hired"
                return result

        # 3. 아무것도 없으면 unknown
        result["deadline"] = ""
        result["deadline_type"] = "unknown"
        return result

    # ========== 전체 크롤링 ==========

    async def crawl_all(
        self,
        max_pages: Optional[int] = None,
        save_callback: Optional[Callable[[List[Dict]], Awaitable[dict]]] = None,
        save_batch_size: int = 500,
    ) -> Tuple[int, Set[str], Dict]:
        """
        전체 크롤링 (목록 + 상세)

        Returns:
            (수집 건수, ID 세트, 저장 통계)
        """
        self.stats.start_time = datetime.now()

        print("=" * 60, flush=True)
        print("[V2] 전체 크롤링 시작", flush=True)
        print(f"  - 워커: {self.num_workers}개", flush=True)
        print(f"  - 프록시: {'ON' if self.use_proxy else 'OFF (폴백 활성화)'}", flush=True)
        print("=" * 60, flush=True)

        # 1. 목록 수집
        job_ids = await self.crawl_list(max_pages)

        if not job_ids:
            logger.warning("수집된 ID 없음")
            return 0, set(), {}

        # 2. 상세 수집
        success_count, save_stats = await self.crawl_details(
            job_ids,
            save_callback=save_callback,
            batch_size=save_batch_size,
        )

        # 결과 출력
        print("=" * 60, flush=True)
        print("[V2] 크롤링 완료", flush=True)
        stats = self.stats.summary()
        for k, v in stats.items():
            print(f"  - {k}: {v}", flush=True)
        print("=" * 60, flush=True)

        return success_count, job_ids, save_stats

    async def close(self):
        """리소스 정리"""
        await self.session_manager.close()
        for client in self.clients:
            await client.aclose()
        self.clients = []
