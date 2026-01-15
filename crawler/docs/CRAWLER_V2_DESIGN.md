# 잡코리아 크롤러 V2 설계서

> **작성일**: 2026-01-15
> **버전**: 2.0
> **상태**: Draft

---

## 1. 개요

### 1.1 배경

현재 크롤러(httpx 기반)는 잡코리아 서버의 페이지네이션이 작동하지 않는 문제로 인해 **전체 63,370건 중 약 700건만 수집** 가능한 상황입니다.

### 1.2 문제 분석

| 문제 | 원인 | 영향 |
|------|------|------|
| 페이지네이션 무시 | 서버가 `page` 파라미터를 무시 | 모든 페이지가 동일한 ~620개 결과 반환 |
| 필터 무시 | `local`, `duty` 파라미터도 무시됨 | 서울 필터링 불가 |
| 중복 데이터 | 페이지마다 97% 중복 | 실질적 수집량 ~700건 |

### 1.3 해결책 발견

**내부 AJAX 엔드포인트** `/Recruit/Home/_GI_List` 발견:
- 세션 쿠키 획득 후 호출 시 **페이지네이션 정상 작동**
- `local=I000` 파라미터로 **서울 필터 적용**
- **httpx로 직접 호출 가능** (Playwright 불필요)

---

## 2. 권장 구현 방식

### 2.1 V2 Lite (1순위) - httpx 기반

```
┌─────────────────────────────────────────────────────────────┐
│                   JobKoreaScraperV2Lite                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  httpx.AsyncClient (세션 유지)                               │
│       │                                                      │
│       ├── 1. GET /recruit/joblist  ──→ 세션/쿠키 획득       │
│       │                                                      │
│       ├── 2. GET /Recruit/Home/_GI_List?Page=N&local=I000   │
│       │       ──→ ✅ 페이지네이션 정상 작동!                 │
│       │       ──→ 페이지당 40개 ID                          │
│       │                                                      │
│       └── 3. GET /Recruit/GI_Read/{id}  ──→ 상세 정보       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**장점:**
- Playwright 없이 동작 → 가볍고 운영 부담 적음
- 메모리: ~200MB (Playwright 대비 10배 절약)
- 설정/배포 간단

### 2.2 V2 Full (2순위) - Playwright 폴백

```
httpx 호출 시 403/차단 발생
        │
        ▼
Playwright로 세션 생성
        │
        ▼
쿠키 추출 → httpx에 전달
        │
        ▼
httpx로 AJAX 호출 재시도
```

**사용 조건:**
- httpx 직접 호출이 차단될 때만 활성화
- 현재 테스트에서는 차단 없음

---

## 3. 검증된 설정

### 3.1 AJAX 엔드포인트

```python
# ✅ 정확한 엔드포인트 (테스트 검증됨)
AJAX_ENDPOINT = "/Recruit/Home/_GI_List"

# ❌ 작동하지 않는 엔드포인트
# "/recruit/_GI_List"  → 404
# "/Recruit/_GI_List"  → 404
```

### 3.2 필수 파라미터

```python
params = {
    "Page": page_num,      # 페이지 번호 (1부터 시작)
    "local": "I000",       # 서울 전체
}

headers = {
    "X-Requested-With": "XMLHttpRequest",  # AJAX 요청 표시
}
```

### 3.3 측정된 성능

| 항목 | 값 | 비고 |
|------|-----|------|
| 페이지당 공고 수 | 40개 | 고정 |
| 고유율 | 100% | 중복 없음 |
| 응답 시간 | 89ms | 평균 |
| 초당 페이지 | 11.4 | 단일 클라이언트 |
| 서울 전체 공고 | 63,370건 | 2026-01-15 기준 |
| 필요 페이지 수 | 1,585개 | 63,370 / 40 |

---

## 4. 아키텍처

### 4.1 V2 Lite 구조

```
crawler/app/
├── scrapers/
│   ├── jobkorea.py           # V1 (기존) - 유지
│   └── jobkorea_v2.py        # V2 Lite (신규)
├── core/
│   ├── ajax_client.py        # AJAX 요청 클라이언트
│   └── session_manager.py    # 세션/쿠키 관리
└── parsers/
    └── list_parser.py        # 목록 HTML 파싱
```

### 4.2 데이터 흐름

```
1. httpx 클라이언트 생성 (쿠키 저장소 포함)
        │
        ▼
2. /recruit/joblist 방문 → 세션 쿠키 획득
   - ASP.NET_SessionId
   - jobkorea
   - 기타 쿠키들
        │
        ▼
3. WorkerPool이 페이지 범위 분배
   - Worker 1: 페이지 1-160
   - Worker 2: 페이지 161-320
   - ...
   - Worker 10: 페이지 1441-1585
        │
        ▼
4. 각 Worker가 AJAX 호출
   GET /Recruit/Home/_GI_List?Page=N&local=I000
   → 페이지당 40개 Job ID 추출 (GI_Read/숫자 패턴)
        │
        ▼
5. 수집된 ID로 상세 페이지 요청
   GET /Recruit/GI_Read/{job_id}
   → salary, description 등 추출
        │
        ▼
6. Firestore에 저장/업데이트
```

---

## 5. 상세 설계

### 5.1 SessionManager (httpx 버전)

```python
class SessionManager:
    """httpx 기반 세션 관리"""

    BASE_URL = "https://www.jobkorea.co.kr"
    JOBLIST_URL = f"{BASE_URL}/recruit/joblist"

    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None

    async def initialize(self) -> httpx.AsyncClient:
        """세션 초기화 및 쿠키 획득"""
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9",
            },
            follow_redirects=True,
        )

        # 세션 쿠키 획득
        await self.client.get(
            self.JOBLIST_URL,
            params={"menucode": "local", "local": "I000"}
        )

        logger.info(f"세션 획득 완료: {list(self.client.cookies.keys())}")
        return self.client

    async def close(self):
        if self.client:
            await self.client.aclose()
```

### 5.2 AjaxClient

```python
class AjaxClient:
    """AJAX 엔드포인트 클라이언트"""

    AJAX_ENDPOINT = "/Recruit/Home/_GI_List"
    BASE_URL = "https://www.jobkorea.co.kr"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def fetch_page(
        self,
        page_num: int,
        local: str = "I000"
    ) -> List[str]:
        """
        목록 페이지 AJAX 호출

        Returns:
            List[str]: 추출된 Job ID 목록
        """
        resp = await self.client.get(
            f"{self.BASE_URL}{self.AJAX_ENDPOINT}",
            params={"Page": page_num, "local": local},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )

        if resp.status_code != 200:
            raise CrawlerError(f"AJAX 호출 실패: {resp.status_code}")

        # GI_Read/숫자 패턴으로 ID 추출
        matches = re.findall(r'GI_Read/(\d+)', resp.text)
        return list(set(matches))

    async def get_total_count(self, local: str = "I000") -> int:
        """전체 공고 수 조회"""
        resp = await self.client.get(
            f"{self.BASE_URL}{self.AJAX_ENDPOINT}",
            params={"Page": 1, "local": local},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )

        match = re.search(r'hdnGICnt.*?value="([\d,]+)"', resp.text)
        if match:
            return int(match.group(1).replace(",", ""))
        return 0
```

### 5.3 WorkerPool (httpx 버전)

```python
class WorkerPool:
    """병렬 워커 관리"""

    def __init__(
        self,
        num_workers: int = 10,
        delay_ms: int = 100
    ):
        self.num_workers = num_workers
        self.delay = delay_ms / 1000
        self.clients: List[httpx.AsyncClient] = []
        self.ajax_clients: List[AjaxClient] = []

    async def initialize(self, session_cookies: httpx.Cookies):
        """워커 초기화 (세션 쿠키 공유)"""
        for i in range(self.num_workers):
            client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": USER_AGENTS[i % len(USER_AGENTS)],
                    "Accept-Language": "ko-KR,ko;q=0.9",
                },
                cookies=session_cookies,  # 세션 공유
                follow_redirects=True,
            )
            self.clients.append(client)
            self.ajax_clients.append(AjaxClient(client))

    async def crawl_pages(
        self,
        page_range: range,
        callback: Callable[[List[str]], Awaitable[None]]
    ) -> int:
        """페이지 범위 크롤링"""
        page_queue = asyncio.Queue()
        for p in page_range:
            await page_queue.put(p)

        async def worker(worker_id: int):
            ajax = self.ajax_clients[worker_id]
            count = 0

            while True:
                try:
                    page_num = page_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                try:
                    ids = await ajax.fetch_page(page_num)
                    await callback(ids)
                    count += len(ids)
                except Exception as e:
                    logger.warning(f"Worker {worker_id} 페이지 {page_num} 실패: {e}")

                await asyncio.sleep(self.delay)

            return count

        results = await asyncio.gather(
            *[worker(i) for i in range(self.num_workers)]
        )
        return sum(results)

    async def close(self):
        for client in self.clients:
            await client.aclose()
```

### 5.4 메인 크롤러

```python
class JobKoreaScraperV2:
    """잡코리아 크롤러 V2 Lite"""

    JOBS_PER_PAGE = 40

    def __init__(
        self,
        num_workers: int = 10,
        use_proxy_for_details: bool = True
    ):
        self.num_workers = num_workers
        self.use_proxy = use_proxy_for_details
        self.session_manager = SessionManager()
        self.worker_pool = None
        self.stats = CrawlerStats()

    async def initialize(self):
        """크롤러 초기화"""
        client = await self.session_manager.initialize()

        self.worker_pool = WorkerPool(num_workers=self.num_workers)
        await self.worker_pool.initialize(client.cookies)

        # 전체 공고 수 확인
        ajax = AjaxClient(client)
        self.total_count = await ajax.get_total_count()
        self.total_pages = (self.total_count // self.JOBS_PER_PAGE) + 1

        logger.info(f"초기화 완료: {self.total_count:,}건, {self.total_pages:,}페이지")

    async def crawl_list(
        self,
        max_pages: Optional[int] = None
    ) -> Set[str]:
        """목록 크롤링 - Job ID 수집"""
        pages = min(self.total_pages, max_pages or self.total_pages)
        collected_ids: Set[str] = set()

        async def on_ids(ids: List[str]):
            collected_ids.update(ids)

        await self.worker_pool.crawl_pages(range(1, pages + 1), on_ids)

        logger.info(f"목록 수집 완료: {len(collected_ids):,}개 ID")
        return collected_ids

    async def crawl_details(
        self,
        job_ids: Set[str],
        save_callback: Optional[Callable] = None
    ) -> int:
        """상세 페이지 크롤링"""
        # 기존 상세 페이지 로직 사용
        # (프록시 적용)
        pass

    async def close(self):
        await self.session_manager.close()
        if self.worker_pool:
            await self.worker_pool.close()
```

---

## 6. 프록시 전략

### 6.1 목록 vs 상세 페이지 차이

| 구분 | 목록 (AJAX) | 상세 페이지 |
|------|-------------|-------------|
| 요청 수 | 1,585회 | **63,370회** |
| 엔드포인트 | 내부 AJAX API | 개별 페이지 URL |
| 패턴 | 세션 기반 탐색 | 대량 개별 접근 |
| 차단 위험 | 낮음 | **높음** |

### 6.2 프록시 필요성 분석

```
⚠️ 중요: 테스트 20건 성공 ≠ 63,370건 안전

목록 수집:
  - 내부 AJAX 엔드포인트 → 일반 사용자 패턴과 유사
  - 세션 쿠키 기반 → 정상적인 페이지 탐색으로 인식
  - 프록시 없이 가능 ✅

상세 수집:
  - 63,370개 개별 URL 접근 → 의심스러운 패턴 가능
  - 동일 IP에서 대량 요청 → 차단 트리거 가능성
  - 권장: 프록시 없이 시작 → 차단 감지 시 프록시 폴백

프록시 선택 시:
  ❌ 다중 IP 세션: 80% 성공률 (실패율 높음)
  ✅ 동일 세션 병렬: 100% 성공률 (권장)
```

### 6.3 권장 프록시 설정

```python
# 목록 수집: 프록시 없음
LIST_CONFIG = {
    "use_proxy": False,
    "num_workers": 10,
    "delay_ms": 100,
}

# 상세 수집: 프록시 없이 시작, 차단 시 폴백
DETAIL_CONFIG = {
    "use_proxy": False,  # 1차: 프록시 없이 시도
    "fallback_proxy": True,  # 차단 시 프록시로 전환
    "num_workers": 10,
    "delay_ms": 50,
}

# 프록시 폴백 설정 (차단 시)
PROXY_FALLBACK_CONFIG = {
    "use_proxy": True,
    "proxy_mode": "same_session",  # 동일 세션 (100% 성공)
    "num_workers": 10,
    "delay_ms": 100,
}
```

### 6.4 IPRoyal 프록시 성능 측정 (2026-01-15)

| 방식 | 속도 | 성공률 | 권장 |
|------|------|--------|------|
| **프록시 없음 5워커** | **12.0건/s** | **100%** | **✅ 1차 시도** |
| **프록시 동일세션 5워커** | **2.2건/s** | **100%** | **✅ 폴백용** |
| 프록시 다중IP 5워커 | 2.2건/s | 80% | ❌ 실패율 높음 |
| 프록시 단일 순차 | 0.4건/s | 100% | ❌ 너무 느림 |

**결론**: 다중 IP 세션은 80% 성공률로 부적합. **동일 세션 병렬**이 100% 성공.

---

## 7. 성능 예측

### 7.1 현실적 예상 성능

```
목록 수집 (프록시 없음, 10워커):
- 총 페이지: 1,585개
- 페이지당: 100ms (딜레이 포함)
- 소요 시간: ~3분

상세 수집 - 시나리오별:

A) 프록시 없이 성공 (차단 안됨):
   - 63,370건 ÷ 24건/s (10워커) = 2,640초 ≈ 44분

B) 중간에 차단 → 프록시 폴백:
   - 전반부 프록시 없음: ~20분
   - 후반부 프록시: ~2시간
   - 총: ~2.5시간

C) 처음부터 프록시 사용:
   - 63,370건 ÷ 4.4건/s (10워커) = 14,402초 ≈ 4시간

예상 시나리오: A 또는 B (44분 ~ 2.5시간)
```

### 7.2 워커 수별 예상 시간

| 워커 수 | 프록시 없음 | 프록시 사용 | 차단 위험 |
|---------|------------|------------|----------|
| 5워커 | 88분 | 4.8시간 | 낮음 |
| **10워커** | **44분** | **4시간** | **낮음~중간** |
| 15워커 | 30분 | 2.7시간 | 중간 |
| 20워커 | 22분 | 2시간 | 중간~높음 |

**권장: 10워커 프록시 없이 시작 → 차단 감지 시 프록시 폴백**

### 7.3 리소스 비교

| 리소스 | V1 | V2 Lite | V2 Full (Playwright) |
|--------|-----|---------|---------------------|
| 메모리 | ~200MB | ~300MB | ~2GB |
| CPU | 낮음 | 낮음 | 중간 |
| 의존성 | httpx | httpx | httpx + playwright |
| 복잡도 | 낮음 | 낮음 | 중간 |

---

## 8. 위험 관리

### 8.1 차단 위험 상세 분석

| 단계 | 요청 수 | 프록시 | 차단 위험 | 근거 |
|------|---------|--------|----------|------|
| 목록 수집 | 1,585 | 없음 | **낮음** | 100회 테스트 통과, 내부 AJAX API |
| 상세 수집 | 63,370 | 없음→폴백 | **중간** | 20건 테스트 OK, 대량은 미확인 |

### 8.2 위험 시나리오

```
❌ 위험한 접근:
  - 프록시 없이 30워커로 63,370건 무작정 요청
  - 차단 감지 없이 계속 요청
  - 차단 시 IP 블랙리스트 등록 가능

✅ 권장 접근 (적응형):
  1. 프록시 없이 10워커로 시작 (12건/s)
  2. 403/429 응답 모니터링
  3. 연속 실패 5회 → 속도 감소 또는 프록시 전환
  4. 프록시 전환 시 동일 세션 병렬 (100% 성공률)
```

### 8.3 차단 감지 및 대응

```python
class AdaptiveRateLimiter:
    """적응형 속도 제한"""

    def __init__(self):
        self.delay = 0.1  # 초기 100ms
        self.consecutive_errors = 0
        self.blocked = False

    def on_success(self):
        self.consecutive_errors = 0
        # 점진적으로 속도 증가 (최소 100ms 유지)
        self.delay = max(0.1, self.delay * 0.95)

    def on_error(self, status_code: int):
        self.consecutive_errors += 1

        if status_code in [403, 429]:
            # 차단 감지: 속도 대폭 감소
            self.delay = min(5.0, self.delay * 3)

            if self.consecutive_errors >= 5:
                self.blocked = True
                logger.error("차단 감지! 크롤링 일시 중단")

    async def wait(self):
        await asyncio.sleep(self.delay)
```

### 8.4 폴백 전략

```python
async def fetch_with_fallback(self, job_id: str) -> Dict:
    """적응형 폴백 전략"""

    # 1차: 프록시 없이 직접 요청 (빠름, 12건/s)
    try:
        return await self.fetch_detail_direct(job_id)
    except BlockedError:
        self.block_count += 1

    # 차단 감지: 프록시 모드로 전환
    if self.block_count >= 5 and not self.proxy_enabled:
        logger.warning("차단 감지! 프록시 모드로 전환")
        self.proxy_enabled = True
        await self.init_proxy_session()  # 동일 세션 프록시

    # 2차: 프록시 동일 세션으로 재시도 (100% 성공, 2.2건/s)
    if self.proxy_enabled:
        try:
            return await self.fetch_detail_with_proxy(job_id)
        except BlockedError:
            pass

    # 3차: Playwright로 브라우저 렌더링 (최후 수단)
    try:
        return await self.fetch_detail_with_playwright(job_id)
    except Exception as e:
        logger.error(f"모든 방법 실패: {job_id}, {e}")
        return None
```

---

## 8. 마이그레이션 계획

### 8.1 단계별 계획

| 단계 | 내용 | 예상 시간 |
|------|------|----------|
| 1 | V2 Lite 모듈 개발 | 1일 |
| 2 | 단위 테스트 | 0.5일 |
| 3 | 1,000건 통합 테스트 | 0.5일 |
| 4 | 전체 크롤링 테스트 | 1일 |
| 5 | 프로덕션 전환 | 0.5일 |

### 8.2 체크리스트

- [ ] `jobkorea_v2.py` 구현
- [ ] `ajax_client.py` 구현
- [ ] 단위 테스트 작성
- [ ] 1,000건 테스트 실행
- [ ] 차단 모니터링 확인
- [ ] 전체 크롤링 테스트
- [ ] 기존 V1과 결과 비교
- [ ] Firestore 저장 검증
- [ ] 프로덕션 배포

---

## 9. 결론

### 9.1 권장 구현

```
1순위: V2 Lite (httpx + AJAX)
 └── 가볍고, 빠르고, 운영 부담 적음

2순위: V2 Full (Playwright 폴백)
 └── 차단 발생 시에만 활성화
```

### 9.2 기대 효과

| 항목 | V1 (현재) | V2 Lite | 개선율 |
|------|----------|---------|--------|
| 수집량 | ~700건 | 63,370건 | **90배** |
| 고유율 | ~1% | 100% | **100배** |
| 목록 수집 | N/A | ~3분 | - |
| 상세 수집 | N/A | 44분~2.5시간 | - |
| 메모리 | 200MB | 300MB | 1.5배 |

### 9.3 핵심 설정

```python
# 반드시 이 설정 사용
AJAX_ENDPOINT = "/Recruit/Home/_GI_List"
AJAX_PARAMS = {"Page": N, "local": "I000"}
AJAX_HEADERS = {"X-Requested-With": "XMLHttpRequest"}

# 세션 획득 (첫 요청)
SESSION_URL = "/recruit/joblist?menucode=local&local=I000"
```

---

## 부록

### A. 테스트 결과 (2026-01-15)

```
엔드포인트 테스트:
  ❌ /recruit/_GI_List → 404
  ✅ /Recruit/Home/_GI_List → 200, 40개 ID

연속 페이지 테스트:
  페이지 1-10: 400개 고유 ID (100%)
  평균 응답: 89ms

30페이지 테스트:
  1,200개 고유 ID
  소요: 2.63초
  속도: 11.4 pages/s
```

### B. 의존성

```
# requirements.txt (V2 Lite는 추가 의존성 없음)
httpx>=0.25.0

# Playwright 폴백 사용 시
playwright>=1.40.0
```
