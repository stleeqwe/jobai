"""잡코리아 크롤러 - 병렬 처리 & 안정성 강화 버전"""

import asyncio
import random
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from bs4 import BeautifulSoup
import httpx

from app.config import settings, USER_AGENTS
from app.normalizers import normalize_job_type, get_job_category, get_mvp_category, normalize_location, parse_salary
from app.normalizers.company import CompanyNormalizer, normalize_company
from app.normalizers.dedup import DedupKeyGenerator, generate_dedup_key

# NOTE: nearest_station 계산은 후처리 배치로 이동 (scripts/enrich_nearest_station.py)


class CrawlerStats:
    """크롤링 통계 추적"""

    MAX_JOB_AGE_DAYS = 30  # 30일 이내 공고만 수집

    def __init__(self):
        self.total_crawled = 0       # 수집된 공고 수 (30일 이내)
        self.total_skipped = 0       # 스킵된 공고 수 (30일 이전)
        self.total_failed = 0        # 실패한 요청 수
        self.consecutive_failures = 0
        self.blocked_detected = False
        self.start_time = None
        self.errors = []

    def record_success(self, count: int = 1):
        """최근 30일 공고 수집 성공"""
        self.total_crawled += count
        self.consecutive_failures = 0

    def record_skip(self, count: int = 1):
        """30일 이전 공고 스킵"""
        self.total_skipped += count

    def record_failure(self, error: str = ""):
        """요청 실패"""
        self.total_failed += 1
        self.consecutive_failures += 1
        if error:
            self.errors.append({"time": datetime.now().isoformat(), "error": error})

    def is_blocked(self) -> bool:
        """차단 감지 (연속 10회 실패 또는 명시적 차단)"""
        return self.blocked_detected or self.consecutive_failures >= 10

    @property
    def failure_rate(self) -> float:
        total = self.total_crawled + self.total_failed
        return self.total_failed / total if total > 0 else 0

    def summary(self) -> dict:
        elapsed = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        return {
            "total_crawled": self.total_crawled,
            "total_skipped": self.total_skipped,
            "total_failed": self.total_failed,
            "failure_rate": f"{self.failure_rate:.1%}",
            "elapsed_seconds": int(elapsed),
            "elapsed_minutes": round(elapsed / 60, 1),
            "is_blocked": self.is_blocked(),
            "recent_errors": self.errors[-5:] if self.errors else [],
        }


class JobKoreaScraper:
    """잡코리아 채용공고 스크래퍼 - 병렬 처리 지원"""

    BASE_URL = "https://www.jobkorea.co.kr"
    LIST_URL = f"{BASE_URL}/recruit/joblist"
    DETAIL_URL = f"{BASE_URL}/Recruit/GI_Read"

    # 크롤링 대상 지역 코드 (MVP: 서울 전체)
    TARGET_LOCAL_CODE = "I000"  # 서울 전체

    # 서울 지역 코드
    SEOUL_LOCAL_CODE = "I000"

    # 서울 구별 코드 (분산 크롤링용)
    SEOUL_GU_CODES = {
        "강남구": "I010", "강동구": "I020", "강북구": "I030", "강서구": "I040",
        "관악구": "I050", "광진구": "I060", "구로구": "I070", "금천구": "I080",
        "노원구": "I090", "도봉구": "I100", "동대문구": "I110", "동작구": "I120",
        "마포구": "I130", "서대문구": "I140", "서초구": "I150", "성동구": "I160",
        "성북구": "I170", "송파구": "I180", "양천구": "I190", "영등포구": "I200",
        "용산구": "I210", "은평구": "I220", "종로구": "I230", "중구": "I240", "중랑구": "I250",
    }

    def __init__(self, num_workers: int = 2):
        """
        Args:
            num_workers: 병렬 워커 수 (기본 2, 최대 3 - 차단 방지)
        """
        self.num_workers = min(num_workers, 3)  # 최대 3개로 제한 (차단 방지)
        self.stats = CrawlerStats()
        self.clients: List[httpx.AsyncClient] = []
        self._setup_clients()

        # Phase 1: Normalizer 인스턴스
        self.company_normalizer = CompanyNormalizer()
        self.dedup_generator = DedupKeyGenerator()

    def _setup_clients(self):
        """워커별 HTTP 클라이언트 설정 (각각 다른 User-Agent)"""
        for i in range(self.num_workers):
            client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": USER_AGENTS[i % len(USER_AGENTS)],
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                },
                follow_redirects=True,
            )
            self.clients.append(client)

    async def close(self):
        """모든 클라이언트 종료"""
        for client in self.clients:
            await client.aclose()

    # ========== 전체 크롤링 (병렬) ==========

    async def crawl_all_parallel(
        self,
        max_pages: Optional[int] = None,
        save_callback: Optional[callable] = None,
        save_batch_size: int = 500,
        start_page: int = 1
    ) -> Tuple[int, set, Dict]:
        """
        병렬 크롤링 (asyncio.Event + 공유 카운터 + Save Queue)

        Args:
            max_pages: 최대 페이지 수 (None이면 전체)
            save_callback: 중간 저장 콜백 함수 (async def save(jobs) -> dict)
            save_batch_size: 중간 저장 배치 크기 (기본 500)
            start_page: 시작 페이지 번호

        Returns:
            (수집된 공고 수, 수집된 ID 세트, 저장 통계) - 메모리 최적화
        """
        self.stats.start_time = datetime.now()
        max_pages = max_pages or 10000
        end_page = start_page + max_pages

        print(f"[Crawler] 병렬 크롤링 시작 (워커: {self.num_workers}개)", flush=True)
        print(f"[Crawler] 요청 간격: {settings.CRAWL_DELAY_SECONDS}초", flush=True)
        print(f"[Crawler] 페이지 범위: {start_page} ~ {end_page - 1}", flush=True)

        # === 공유 상태 (asyncio.Event + 카운터) ===
        stop_event = asyncio.Event()  # 전역 종료 신호
        page_lock = asyncio.Lock()
        next_page = start_page

        # === Save Queue (워커 → Saver 분리) ===
        save_queue: asyncio.Queue = asyncio.Queue()
        total_collected = 0  # 메모리 최적화: 리스트 대신 카운터
        collected_ids: set = set()  # ID 세트만 추적 (mark_expired_jobs용)
        total_saved = {"new": 0, "updated": 0, "failed": 0}
        saver_done = asyncio.Event()

        async def get_next_page() -> Optional[int]:
            """다음 페이지 번호 반환 (종료 시 None)"""
            nonlocal next_page
            async with page_lock:
                if next_page >= end_page or stop_event.is_set():
                    return None
                page = next_page
                next_page += 1
                return page

        async def saver_task():
            """저장 전용 태스크 (워커와 분리)"""
            nonlocal total_collected
            pending: List[Dict] = []

            while True:
                try:
                    # 타임아웃으로 주기적으로 저장 체크
                    job = await asyncio.wait_for(save_queue.get(), timeout=2.0)
                    if job is None:  # 종료 신호
                        break
                    pending.append(job)
                    total_collected += 1
                    collected_ids.add(job.get("id"))

                    # 배치 크기 도달 시 저장
                    if len(pending) >= save_batch_size and save_callback:
                        to_save = pending[:]
                        pending = []
                        try:
                            result = await save_callback(to_save)
                            total_saved["new"] += result.get("new", 0)
                            total_saved["updated"] += result.get("updated", 0)
                            total_saved["failed"] += result.get("failed", 0)
                            print(f"[Saver] 저장 완료: {len(to_save)}건 (총: {total_saved['new'] + total_saved['updated']}건)", flush=True)
                        except Exception as e:
                            print(f"[Saver] 저장 실패: {e}", flush=True)
                            pending.extend(to_save)

                except asyncio.TimeoutError:
                    # 타임아웃 시 중간 저장 (종료 대기 중)
                    if stop_event.is_set() and pending and save_callback:
                        try:
                            result = await save_callback(pending)
                            total_saved["new"] += result.get("new", 0)
                            total_saved["updated"] += result.get("updated", 0)
                            pending = []
                        except Exception:
                            pass
                    continue

            # 남은 데이터 저장
            if pending and save_callback:
                try:
                    result = await save_callback(pending)
                    total_saved["new"] += result.get("new", 0)
                    total_saved["updated"] += result.get("updated", 0)
                    print(f"[Saver] 최종 저장: {len(pending)}건", flush=True)
                except Exception as e:
                    print(f"[Saver] 최종 저장 실패: {e}", flush=True)

            saver_done.set()

        async def worker(worker_id: int):
            """크롤링 워커 (저장은 save_queue로 위임)"""
            client = self.clients[worker_id]
            local_count = 0

            while not stop_event.is_set() and not self.stats.is_blocked():
                page = await get_next_page()
                if page is None:
                    break

                try:
                    prev_skip_count = self.stats.total_skipped
                    result = await self._crawl_page_with_client(client, page, worker_id)

                    # 반환값 해석
                    if result is None:  # 공고 없음 또는 차단
                        print(f"[Worker-{worker_id}] 페이지 {page}: 공고 없음, 전체 종료 신호", flush=True)
                        stop_event.set()
                        break

                    jobs = result

                    # 30일 이전 공고만 있는 페이지 감지
                    page_skip_count = self.stats.total_skipped - prev_skip_count
                    if len(jobs) == 0 and page_skip_count > 10:
                        print(f"[Worker-{worker_id}] 페이지 {page}: 30일 이전만 {page_skip_count}건, 종료", flush=True)
                        stop_event.set()
                        break

                    # Save Queue에 추가 (블로킹 없이)
                    for job in jobs:
                        await save_queue.put(job)

                    local_count += len(jobs)
                    self.stats.record_success(len(jobs))

                    if page % 10 == 0 or page <= 3:
                        print(f"[Worker-{worker_id}] 페이지 {page}: {len(jobs)}건 (누적 {local_count}건)", flush=True)

                    # 요청 간 딜레이
                    delay = settings.CRAWL_DELAY_SECONDS + random.uniform(0.1, 0.5)
                    await asyncio.sleep(delay)

                except Exception as e:
                    self.stats.record_failure(str(e))
                    print(f"[Worker-{worker_id}] 페이지 {page} 실패: {e}", flush=True)

                    if self.stats.is_blocked():
                        print(f"[Worker-{worker_id}] 차단 감지! 전체 종료", flush=True)
                        stop_event.set()
                        break

                    await asyncio.sleep(settings.CRAWL_DELAY_SECONDS * 3)

            print(f"[Worker-{worker_id}] 종료 (수집: {local_count}건)", flush=True)

        # === 실행 ===
        # 1. Saver 태스크 시작
        saver = asyncio.create_task(saver_task())

        # 2. 워커들 실행
        workers = [worker(i) for i in range(self.num_workers)]
        await asyncio.gather(*workers)

        # 3. Saver 종료 신호 및 대기
        await save_queue.put(None)
        await saver

        print(f"\n[Crawler] 크롤링 완료", flush=True)
        print(f"[Crawler] 수집: {total_collected}건", flush=True)
        print(f"[Crawler] 통계: {self.stats.summary()}", flush=True)
        print(f"[Crawler] 저장: 신규 {total_saved['new']}건, 업데이트 {total_saved['updated']}건", flush=True)

        # 메모리 최적화: 전체 dict 대신 ID 세트만 반환
        return total_collected, collected_ids, total_saved

    async def _crawl_page_with_client(
        self, client: httpx.AsyncClient, page: int, worker_id: int,
        parallel_batch_size: int = 5
    ) -> Optional[List[Dict]]:
        """
        특정 클라이언트로 페이지 크롤링 (상세 페이지 병렬 호출)

        Args:
            client: HTTP 클라이언트
            page: 페이지 번호
            worker_id: 워커 ID
            parallel_batch_size: 병렬 호출 배치 크기 (기본 5)
        """
        params = {
            "menucode": "local",
            "local": self.TARGET_LOCAL_CODE,
            "page": page,
        }

        response = await self._fetch_with_retry(client, self.LIST_URL, params=params)
        if not response:
            return None

        # 차단 감지
        if self._detect_blocking(response):
            self.stats.blocked_detected = True
            return None

        soup = BeautifulSoup(response.text, "lxml")

        # 셀렉터 우선순위: li.devloopArea (663건) > li.job-recommendation-item (3건)
        job_items = soup.select("li.devloopArea")
        if not job_items:
            job_items = soup.select("li.job-recommendation-item")

        if not job_items:
            return None  # 더 이상 공고 없음

        # 1단계: 모든 아이템에서 기본 정보 파싱
        parsed_jobs = []
        for item in job_items:
            try:
                job = self._parse_job_item(item)
                if job and job.get("id"):
                    parsed_jobs.append(job)
            except Exception as e:
                if settings.DEBUG:
                    print(f"[Worker-{worker_id}] 아이템 파싱 실패: {e}")
                continue

        # 30일 필터링용 기준일
        cutoff_date = datetime.now() - timedelta(days=CrawlerStats.MAX_JOB_AGE_DAYS)

        # 2단계: 상세 페이지 병렬 호출 (배치 단위)
        async def fetch_detail_with_delay(job: Dict, batch_idx: int) -> Dict:
            """상세 정보 가져오기 (배치 내 딜레이 적용, 30일 필터링)"""
            try:
                job_id = job["id"].replace("jk_", "")
                detail_info = await self._fetch_detail_info(client, job_id, cutoff_date)
                if detail_info:
                    # 30일 이전 공고는 스킵
                    if detail_info.get("_skip"):
                        job["_skip"] = True
                        job["posted_at"] = detail_info.get("posted_at")
                    else:
                        job.update(detail_info)
            except Exception as e:
                if settings.DEBUG:
                    print(f"[Worker-{worker_id}] 상세 정보 실패 ({job['id']}): {e}")
            return job

        jobs = []
        for batch_start in range(0, len(parsed_jobs), parallel_batch_size):
            batch = parsed_jobs[batch_start:batch_start + parallel_batch_size]

            # 배치 내 병렬 호출
            tasks = [
                fetch_detail_with_delay(job, i)
                for i, job in enumerate(batch)
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # 성공한 결과만 추가 (30일 이전 공고 제외)
            for result in batch_results:
                if isinstance(result, dict):
                    if result.get("_skip"):
                        self.stats.record_skip()
                    else:
                        jobs.append(result)

            # 배치 간 딜레이 (차단 방지)
            if batch_start + parallel_batch_size < len(parsed_jobs):
                await asyncio.sleep(0.8 + random.uniform(0.2, 0.4))  # 0.8~1.2초

        return jobs

    # ========== 증분 업데이트 (최신 N건) ==========

    async def crawl_latest(self, count: int = 200, parallel_batch_size: int = 5) -> List[Dict]:
        """
        최신 공고 N건 수집 (매시간 업데이트용) - 병렬 처리

        Args:
            count: 수집할 공고 수 (기본 200, 피크시간 500)
            parallel_batch_size: 상세 페이지 병렬 호출 배치 크기

        Returns:
            최신 채용공고 리스트
        """
        self.stats.start_time = datetime.now()
        client = self.clients[0]
        all_jobs: List[Dict] = []
        page = 1
        cutoff_date = datetime.now() - timedelta(days=CrawlerStats.MAX_JOB_AGE_DAYS)

        print(f"[Crawler] 최신 공고 {count}건 수집 시작 (30일 이내, 병렬 {parallel_batch_size})", flush=True)

        while len(all_jobs) < count:
            try:
                params = {
                    "menucode": "local",
                    "local": self.TARGET_LOCAL_CODE,
                    "page": page,
                    "orderby": "reg",  # 최신순 정렬
                }

                response = await self._fetch_with_retry(client, self.LIST_URL, params=params)
                if not response:
                    break

                soup = BeautifulSoup(response.text, "lxml")
                job_items = soup.select("li.job-recommendation-item, .devloopArea")

                if not job_items:
                    break

                # 1단계: 목록에서 기본 정보 파싱
                parsed_jobs = []
                for item in job_items:
                    if len(all_jobs) + len(parsed_jobs) >= count:
                        break
                    try:
                        job = self._parse_job_item(item)
                        if job and job.get("id"):
                            parsed_jobs.append(job)
                    except Exception:
                        continue

                # 2단계: 상세 페이지 병렬 호출 (배치 단위)
                async def fetch_detail(job: Dict) -> Dict:
                    try:
                        job_id = job["id"].replace("jk_", "")
                        detail_info = await self._fetch_detail_info(client, job_id, cutoff_date)
                        if detail_info:
                            if detail_info.get("_skip"):
                                job["_skip"] = True
                            else:
                                job.update(detail_info)
                    except Exception:
                        pass
                    return job

                for batch_start in range(0, len(parsed_jobs), parallel_batch_size):
                    batch = parsed_jobs[batch_start:batch_start + parallel_batch_size]
                    tasks = [fetch_detail(job) for job in batch]
                    batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                    for result in batch_results:
                        if isinstance(result, dict):
                            if result.get("_skip"):
                                self.stats.record_skip()
                            else:
                                all_jobs.append(result)
                                if len(all_jobs) >= count:
                                    break

                    # 배치 간 딜레이
                    if batch_start + parallel_batch_size < len(parsed_jobs):
                        await asyncio.sleep(0.5)

                    if len(all_jobs) >= count:
                        break

                self.stats.record_success(len(parsed_jobs))
                page += 1
                await asyncio.sleep(settings.CRAWL_DELAY_SECONDS)

            except Exception as e:
                self.stats.record_failure(str(e))
                print(f"[Crawler] 페이지 {page} 실패: {e}", flush=True)
                break

        print(f"[Crawler] 최신 공고 수집 완료: {len(all_jobs)}건", flush=True)
        return all_jobs

    # ========== URL 검증 (404 체크) ==========

    async def verify_jobs(self, job_ids: List[str]) -> Dict[str, bool]:
        """
        공고 URL 유효성 검증 (HEAD 요청)

        Args:
            job_ids: 검증할 공고 ID 리스트 (jk_XXXXX 형식)

        Returns:
            {job_id: is_valid} 딕셔너리
        """
        print(f"[Crawler] {len(job_ids)}건 URL 검증 시작")
        results = {}
        client = self.clients[0]

        for i, job_id in enumerate(job_ids):
            try:
                raw_id = job_id.replace("jk_", "")
                url = f"{self.DETAIL_URL}/{raw_id}"

                # HEAD 요청으로 가볍게 체크
                response = await client.head(url, follow_redirects=True)
                is_valid = response.status_code == 200
                results[job_id] = is_valid

                if not is_valid:
                    print(f"[Crawler] 만료 감지: {job_id} (status: {response.status_code})")

                # 진행 상황 출력
                if (i + 1) % 100 == 0:
                    print(f"[Crawler] 검증 진행: {i + 1}/{len(job_ids)}")

                await asyncio.sleep(0.2)  # HEAD 요청은 빠르므로 짧은 딜레이

            except Exception as e:
                results[job_id] = False  # 에러 시 만료로 처리
                if settings.DEBUG:
                    print(f"[Crawler] 검증 실패 ({job_id}): {e}")

        valid_count = sum(1 for v in results.values() if v)
        print(f"[Crawler] 검증 완료: 유효 {valid_count}건, 만료 {len(results) - valid_count}건")

        return results

    # ========== 내부 메서드 ==========

    def _detect_blocking(self, response: httpx.Response) -> bool:
        """차단/캡차 감지"""
        if response.status_code == 429:
            return True
        if response.status_code == 403:
            return True

        # 캡차 페이지 감지
        text = response.text.lower()
        if "captcha" in text or "보안문자" in text:
            return True
        if "비정상적인" in text or "접근이 차단" in text:
            return True

        return False

    async def _fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict = None,
        max_retries: int = 3
    ) -> Optional[httpx.Response]:
        """지수 백오프 재시도 로직"""
        for attempt in range(max_retries):
            try:
                response = await client.get(url, params=params)

                # 429 Too Many Requests
                if response.status_code == 429:
                    wait_time = 2 ** (attempt + 2)  # 4, 8, 16초
                    print(f"[Crawler] Rate limited, {wait_time}초 대기...")
                    await asyncio.sleep(wait_time)
                    continue

                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return None
                if attempt == max_retries - 1:
                    raise
                wait_time = 2 ** attempt  # 1, 2, 4초
                await asyncio.sleep(wait_time)

            except httpx.RequestError:
                if attempt == max_retries - 1:
                    raise
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)

        return None

    async def _fetch_detail_info(
        self, client: httpx.AsyncClient, job_id: str, cutoff_date: datetime = None
    ) -> Optional[Dict]:
        """상세 페이지에서 직무 정보 추출 (30일 조기 필터링 지원)"""
        try:
            url = f"{self.DETAIL_URL}/{job_id}"
            response = await self._fetch_with_retry(client, url, max_retries=2)
            if not response:
                return None

            html = response.text

            # 30일 조기 필터링: posted_at 먼저 추출하여 스킵 여부 결정
            if cutoff_date:
                posted_at = self._extract_posted_at(html)
                if posted_at and posted_at < cutoff_date:
                    return {"_skip": True, "posted_at": posted_at}

            # 1. workFields 추출
            work_fields_match = re.search(r'workFields\\\\?":\[([^\]]*)\]', html)
            work_fields = []
            if work_fields_match:
                content = work_fields_match.group(1)
                work_fields = re.findall(r'\\\\?"([^\\\\\"]+)\\\\?"', content)
                if not work_fields:
                    work_fields = re.findall(r'"([^"]+)"', content)

            # 2. 제목에서 직무 키워드 추출 (백업)
            title_match = re.search(r'<title>([^<]+)</title>', html)
            title = title_match.group(1) if title_match else ""

            job_keywords_pattern = [
                "개발자", "디자이너", "마케터", "기획자", "영업", "PM", "PO",
                "백엔드", "프론트엔드", "풀스택", "데이터", "AI", "ML",
                "바리스타", "매니저", "관리자", "엔지니어", "분석가",
                "회계", "인사", "총무", "비서", "CS", "상담사", "연구원",
                "사무", "경리", "교사", "강사", "의사", "간호사", "약사"
            ]

            title_keywords = [kw for kw in job_keywords_pattern if kw in title]

            # 3. workFields 필터링
            location_keywords = ["점", "역", "동", "구", "시", "로", "길", "팝업", "직영"]
            valid_work_fields = []
            for wf in work_fields:
                is_location = any(loc in wf for loc in location_keywords)
                is_job = any(kw in wf for kw in job_keywords_pattern)
                if is_job or (not is_location and len(wf) > 1):
                    valid_work_fields.append(wf)

            job_types = valid_work_fields if valid_work_fields else title_keywords

            # 4. 급여 정보 추출 (여러 패턴 시도)
            salary_text = ""
            salary_patterns = [
                # 범위 패턴 (가장 정확)
                r'(월급?\s*[\d,]+\s*~\s*[\d,]+\s*만원)',
                r'(연봉?\s*[\d,]+\s*~\s*[\d,]+\s*만원)',
                r'([\d,]+\s*~\s*[\d,]+\s*만원)',
                # 단일 금액 패턴
                r'(월급?\s*[\d,]+\s*만원)',
                r'(연봉?\s*[\d,]+\s*만원)',
                # JSON 형식
                r'salaryName["\s:]+([^"]+)"',
                # 협의/내규 패턴
                r'급여[^:]*[:：]\s*(회사\s*내규[^,\n<]*)',
                r'급여[^:]*[:：]\s*(면접\s*후\s*결정[^,\n<]*)',
                r'급여[^:]*[:：]\s*(추후\s*협의[^,\n<]*)',
            ]

            for pattern in salary_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    extracted = match.group(1).strip()
                    # HTML 태그 제거
                    extracted = re.sub(r'<[^>]+>', '', extracted)
                    extracted = re.sub(r'["\'/].*', '', extracted).strip()
                    # 의미 있는 급여 정보인지 확인
                    if extracted and len(extracted) < 30:
                        salary_text = extracted
                        break

            # 5. 급여 파싱 (구조화)
            salary_data = parse_salary(salary_text)

            # 6. 회사 주소 추출 (JSON-LD 우선)
            company_address = ""

            # 6-1. JSON-LD addressLocality 추출 (가장 정확)
            json_ld_match = re.search(r'"addressLocality"\s*:\s*"([^"]+)"', html)
            if json_ld_match:
                company_address = json_ld_match.group(1).strip()

            # 6-2. JSON-LD 없으면 기존 패턴으로 추출
            if not company_address:
                address_patterns = [
                    r'(서울[^\n<,]{5,50}(?:동|로|길)[^\n<,]{0,20})',
                    r'(경기[^\n<,]{5,50}(?:동|로|길)[^\n<,]{0,20})',
                    r'(인천[^\n<,]{5,50}(?:동|로|길)[^\n<,]{0,20})',
                    r'(부산[^\n<,]{5,50}(?:동|로|길)[^\n<,]{0,20})',
                    r'근무지역\s*[:：]\s*([^\n<]{10,50})',
                    r'근무지\s*[:：]\s*([^\n<]{10,50})',
                ]
                for pattern in address_patterns:
                    match = re.search(pattern, html)
                    if match:
                        addr = match.group(1).strip()
                        addr = re.sub(r'\s*\([^)]*$', '', addr)
                        addr = re.sub(r'["\'/].*', '', addr).strip()
                        if addr and 10 <= len(addr) <= 60:
                            company_address = addr
                            break

            # 7. 기업규모 추출
            company_size = ""
            size_match = re.search(
                r'(중소기업|중견기업|대기업|대기업\(계열사\)|스타트업|외국계|공기업|공공기관|비영리)',
                html
            )
            if size_match:
                company_size = size_match.group(1)

            # 8. 복리후생 키워드 추출
            benefits = []
            benefit_keywords = [
                '4대보험', '국민연금', '건강보험', '고용보험', '산재보험',
                '퇴직금', '연차', '월차', '경조사', '경조금', '명절', '보너스', '인센티브', '성과급',
                '점심', '식대', '중식', '석식', '야근수당', '교통비', '주차지원',
                '재택근무', '유연근무', '자율출퇴근', '원격근무', '리모트',
                '교육지원', '자기개발', '도서구입', '학원비', '어학지원', '자격증',
                '건강검진', '의료비', '단체보험', '휴게실', '카페테리아', '체력단련실',
                '스톡옵션', '우리사주', '주택자금', '생일휴가', '안식년'
            ]
            for kw in benefit_keywords:
                if kw in html:
                    benefits.append(kw)

            # 9. 업무내용 추출 (간략)
            job_description = ""
            desc_patterns = [
                r'담당업무[^:]*[:：]\s*([^<\n]{20,300})',
                r'주요업무[^:]*[:：]\s*([^<\n]{20,300})',
                r'업무내용[^:]*[:：]\s*([^<\n]{20,300})',
                r'직무내용[^:]*[:：]\s*([^<\n]{20,300})',
            ]
            for pattern in desc_patterns:
                match = re.search(pattern, html)
                if match:
                    desc = match.group(1).strip()
                    desc = re.sub(r'<[^>]+>', ' ', desc)
                    desc = re.sub(r'\s+', ' ', desc).strip()
                    if len(desc) >= 20:
                        job_description = desc[:500]  # 최대 500자
                        break

            # 10. 마감일 정보 추출 (상세)
            deadline_info = self._extract_deadline_info(html)

            # 11. 정규화
            primary_job_type = job_types[0] if job_types else ""
            normalized = normalize_job_type(primary_job_type) if primary_job_type else ""
            category = get_job_category(normalized) if normalized else "기타"
            mvp_category = get_mvp_category(category)

            # 주소에서 location 정보 추출
            location_info = normalize_location(company_address) if company_address else {}

            # NOTE: nearest_station은 후처리 배치에서 계산 (크롤링 속도 최적화)

            result = {
                "job_type": normalized or primary_job_type,
                "job_type_raw": ", ".join(job_types[:3]),
                "job_category": category,
                "mvp_category": mvp_category,
                "job_keywords": job_types[:5],
                "industry": "",
                "salary_text": salary_data["text"],
                "salary_min": salary_data["min"],
                "salary_max": salary_data["max"],
                "salary_type": salary_data["type"],
                "salary_source": salary_data.get("source", "parsed"),
                "company_size": company_size,
                "benefits": benefits,
                "job_description": job_description,
                **deadline_info,
            }

            # 위치 정보: 상세 페이지에서 추출한 경우에만 덮어씀 (빈 값 방지)
            if company_address:
                result["company_address"] = company_address
                result["location_full"] = company_address
                if location_info.get("sido"):
                    result["location_sido"] = location_info["sido"]
                if location_info.get("gugun"):
                    result["location_gugun"] = location_info["gugun"]
                if location_info.get("dong"):
                    result["location_dong"] = location_info["dong"]

            return result

        except Exception as e:
            if settings.DEBUG:
                print(f"[Crawler] 상세 정보 추출 실패 ({job_id}): {e}")
            return None

    def _extract_posted_at(self, html: str) -> Optional[datetime]:
        """공고 등록일만 빠르게 추출 (30일 필터링용)"""
        posted_patterns = [
            r'applicationStartAt["\\\s:]*"?(\d{4}-\d{2}-\d{2}T[0-9:+\-]+)',
            r'applyStartDate["\\\s:]*"?(\d{4}-\d{2}-\d{2})',
            r'datePosted["\\\s:]*"?(\d{4}-\d{2}-\d{2})',
        ]
        for pattern in posted_patterns:
            match = re.search(pattern, html)
            if match:
                date_str = match.group(1).strip()
                try:
                    if "T" in date_str:
                        return datetime.fromisoformat(
                            date_str.replace("+09:00", "").replace("Z", "")
                        )
                    elif "-" in date_str:
                        return datetime.strptime(date_str[:10], "%Y-%m-%d")
                except:
                    pass
        return None

    def _extract_deadline_info(self, html: str) -> Dict:
        """마감일 정보 상세 추출"""
        result = {
            "deadline": "",
            "deadline_type": "unknown",
            "deadline_date": None,
        }

        # 마감일 패턴들
        patterns = [
            (r'applicationEndAt[\\"]?:[\\"]?([^"\\,]+)', "date"),
            (r'applyCloseDate[\\"]?:[\\"]?([^"\\,]+)', "date"),
            (r'상시채용', "ongoing"),
            (r'채용시\s*마감', "until_hired"),
            (r'~(\d{2}\.\d{2})', "date"),
            (r'~(\d{4}-\d{2}-\d{2})', "date"),
        ]

        for pattern, dtype in patterns:
            match = re.search(pattern, html)
            if match:
                if dtype == "ongoing":
                    result["deadline"] = "상시채용"
                    result["deadline_type"] = "ongoing"
                elif dtype == "until_hired":
                    result["deadline"] = "채용시 마감"
                    result["deadline_type"] = "until_hired"
                elif dtype == "date":
                    date_str = match.group(1).strip()
                    result["deadline"] = date_str
                    result["deadline_type"] = "date"
                    # 날짜 파싱 시도
                    try:
                        if "T" in date_str:
                            result["deadline_date"] = datetime.fromisoformat(
                                date_str.replace("+09:00", "").replace("Z", "")
                            )
                        elif "-" in date_str:
                            result["deadline_date"] = datetime.strptime(date_str[:10], "%Y-%m-%d")
                    except:
                        pass
                break

        return result

    def _parse_job_item(self, item) -> Optional[Dict]:
        """채용공고 아이템 파싱 (목록 페이지) - 2026년 HTML 구조"""
        # 공고 ID 추출 (data-info 속성에서)
        data_info = item.get("data-info", "")
        job_id = None
        if data_info:
            parts = data_info.strip().split("|")
            if parts and parts[0].isdigit():
                job_id = parts[0].strip()

        if not job_id:
            return None

        # 제목 추출 (.description a .text)
        title_el = item.select_one(".description a .text")
        title = title_el.get_text(strip=True) if title_el else ""

        if not title:
            return None

        # 회사명 추출 (.company .name a)
        company_el = item.select_one(".company .name a")
        company_name = ""
        if company_el:
            # a 태그 내에서 span.logo 제외한 텍스트만 추출
            for child in company_el.children:
                if isinstance(child, str):
                    company_name += child.strip()
                elif hasattr(child, 'name') and child.name != 'span':
                    company_name += child.get_text(strip=True)
            company_name = company_name.strip()

        # 링크 추출
        link_el = item.select_one(".description a")
        href = link_el.get("href", "") if link_el else ""

        # 태그 정보 추출
        tags = item.select(".tags-wrapper .tag, .tag")

        experience_raw = ""
        education_raw = ""
        location_raw = ""
        employment_type = "정규직"

        for tag in tags:
            text = tag.get_text(strip=True)
            if not text:
                continue

            if any(kw in text for kw in ["신입", "경력", "년↑", "년이상"]):
                experience_raw = text
            elif any(kw in text for kw in ["졸", "학력", "대학", "고등", "석사", "박사", "초대졸"]):
                education_raw = text
            elif "서울" in text or text.endswith("구"):
                location_raw = text
            elif text in ["정규직", "계약직", "인턴", "프리랜서", "아르바이트", "파트타임"]:
                employment_type = text

        # 마감일 추출 (.dday .deadLine)
        deadline = ""
        dday_el = item.select_one(".dday .deadLine")
        if not dday_el:
            dday_el = item.select_one("[class*='dday'], [class*='deadline']")
        if dday_el:
            deadline = dday_el.get_text(strip=True)

        # 정규화
        location_info = normalize_location(location_raw)
        experience_type, experience_min, experience_max = self._parse_experience(experience_raw)

        # Phase 1: 회사명 정규화
        company_name_normalized, company_type = self.company_normalizer.normalize(company_name)

        # URL 생성
        if href.startswith("http"):
            url = href
        elif href.startswith("/"):
            url = f"{self.BASE_URL}{href}"
        else:
            url = f"{self.BASE_URL}/Recruit/GI_Read/{job_id}"

        now = datetime.now()

        # 기본 데이터 구성
        job_data = {
            "id": f"jk_{job_id}",
            "source": "jobkorea",
            "company_name_raw": company_name,           # Phase 1: 원본 회사명
            "company_name": company_name_normalized,    # Phase 1: 정규화된 회사명
            "company_type": company_type,               # Phase 1: 법인유형 (stock/limited/partnership/None)
            "title": title,
            "url": url,
            "job_type": "",
            "job_type_raw": "",
            "job_category": "기타",
            "mvp_category": "기타",
            "job_keywords": [],
            "location_sido": location_info.get("sido", "서울"),
            "location_gugun": location_info.get("gugun", ""),
            "location_dong": location_info.get("dong", ""),
            "location_full": location_info.get("full", location_raw),
            "experience_type": experience_type,
            "experience_min": experience_min,
            "experience_max": experience_max,
            "education": education_raw,
            "employment_type": employment_type,
            "salary_text": "",
            "salary_min": None,
            "salary_max": None,
            "salary_type": None,
            "salary_source": "unknown",                 # Phase 1: 급여 출처 (상세에서 업데이트)
            "deadline": deadline,
            "deadline_type": "date" if deadline else "ongoing",
            "deadline_date": None,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            "last_verified": now,
        }

        # Phase 1: 중복 제거용 키 생성
        job_data["dedup_key"] = self.dedup_generator.generate(job_data)

        return job_data

    def _parse_experience(self, text: str) -> tuple:
        """경력 텍스트 파싱"""
        if not text:
            return "경력무관", None, None

        if "신입" in text and "경력" in text:
            return "경력무관", None, None
        elif "신입" in text:
            return "신입", 0, 0
        elif "경력무관" in text or "무관" in text:
            return "경력무관", None, None
        elif "경력" in text or "년" in text:
            numbers = re.findall(r"(\d+)", text)
            if len(numbers) >= 2:
                return "경력", int(numbers[0]), int(numbers[1])
            elif len(numbers) == 1:
                return "경력", int(numbers[0]), None
            return "경력", None, None

        return "경력무관", None, None


