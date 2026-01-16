# 잡코리아 크롤러 V2

> **최종 업데이트**: 2026-01-16
> **버전**: 2.2 (Refactored)

---

## 1. 개요

### 현재 상태

| 항목 | 값 |
|------|-----|
| **버전** | V2 Lite (httpx + AJAX) |
| **서울 전체 공고** | ~51,000건 (구별 중복 제거 후) |
| **API 제한** | **250페이지 (10,000건)** |
| **실측 수집량** | 51,000건 전체 (구별 분할 크롤링) |
| **수집 속도** | 12-18건/s (30워커, 프록시 풀 30개) |
| **프록시** | IPRoyal Residential (30개 세션 병렬) |

### 핵심 기술

```
AJAX 엔드포인트: /Recruit/Home/_GI_List
├── 페이지네이션 정상 작동 (단, 250페이지 제한)
├── 세션 쿠키 기반 인증
└── 페이지당 40개 ID 반환
```

### ⚠️ API 제한 사항

**잡코리아 AJAX API는 페이지 제한이 있음 (시간대별 가변)**

```
검증 결과 (2026-01-16):
- 낮 시간: 500페이지까지 작동
- 야간/새벽: 250페이지 제한 (이후 동일 결과 반환)

제한 우회: 구별 필터 크롤링으로 전체 수집 가능
```

전체 64,000건 수집: **구별 필터 병렬 크롤링** 사용 (섹션 7.4 참조)

---

## 2. 아키텍처

### 데이터 흐름

```
┌─────────────────────────────────────────────────────────────┐
│  1. 세션 초기화                                              │
│     GET /recruit/joblist → 세션 쿠키 획득                    │
│     (ASP.NET_SessionId, jobkorea, CookieNo 등)              │
│                                                              │
│  2. 목록 수집 (구별 분할 병렬)                                │
│     GET /Recruit/Home/_GI_List?Page=N&local=I0XX            │
│     → 25개 구별로 분할하여 API 제한 우회                      │
│     → 구별 합계 ~69,000건 → 중복 제거 후 ~51,000건           │
│                                                              │
│  3. 상세 수집 (30워커 병렬)                                   │
│     GET /Recruit/GI_Read/{job_id}                           │
│     → JSON-LD + HTML 파싱                                    │
│     → 제목 토큰 추출 → job_keywords 병합                     │
│                                                              │
│  4. DB 저장 (500건 배치)                                     │
│     Firestore upsert                                         │
│     → new / updated / failed 카운트                          │
└─────────────────────────────────────────────────────────────┘
```

### 파일 구조

```
crawler/app/
├── config.py                # 크롤러 상수 중앙화
├── exceptions.py            # 커스텀 예외 (BlockedError, ParseError 등)
├── scrapers/
│   └── jobkorea_v2.py       # V2 메인 크롤러 (오케스트레이션)
├── parsers/
│   └── detail_parser.py     # 상세 페이지 파서 (JSON-LD/CSS/정규식)
├── workers/
│   └── detail_worker.py     # 상세 크롤링 오케스트레이터
├── core/
│   ├── session_manager.py   # 세션/프록시 관리
│   └── ajax_client.py       # AJAX 클라이언트 + Rate Limiter
├── normalizers/             # 데이터 정규화 모듈
└── db/
    └── firestore.py         # DB 저장
```

---

## 3. 실행 방법

### ⚠️ 실행 전 필수 확인사항

**절대 임의로 진행하지 말 것! 반드시 사용자에게 확인 후 진행.**

#### 1. 프록시 설정 확인 (필수)

```bash
cat .env | grep PROXY_
```

**필수 환경변수:**
```
PROXY_HOST=geo.iproyal.com
PROXY_PORT=12321
PROXY_USERNAME=<사용자명>
PROXY_PASSWORD=<비밀번호>
```

- 4개 모두 설정되어야 함
- 누락 시 → **즉시 중단, 사용자에게 설정 요청**
- ❌ 프록시 없이 임의로 진행 금지!

#### 2. 설정 누락/오류 시 대응

- ❌ 임의로 대체 모드로 진행
- ✅ 즉시 중단하고 사용자에게 보고 및 확인 요청

#### 3. 크롤링 중 모니터링 필수

| 항목 | 정상 범위 | 이상 시 조치 |
|------|----------|-------------|
| 속도 | 12-18건/s | 프록시/워커 수 확인 |
| 403/429 | 0회 | 즉시 중단, 보고 |
| 404 비율 | 10% 이하 | 정상 (삭제된 공고) |

#### 4. 이상 발견 시

1. 즉시 사용자에게 보고
2. 조치 방안 제시
3. 사용자 승인 후 진행

### 실행 스크립트

```bash
cd crawler && source venv/bin/activate

# 전체 크롤링 (64,000건)
python run_crawler.py

# 증분 크롤링 (신규만)
python run_crawler.py --skip-existing

# 목록만 수집
python run_crawler.py --list-only

# 데이터 품질 검증
python test_e2e_quality.py
```

### 주요 설정 (run_crawler.py)

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `num_workers` | 30 | 병렬 워커 수 |
| `use_proxy` | True | 프록시 사용 (필수) |
| `proxy_pool_size` | 30 | 프록시 풀 크기 |
| `save_batch_size` | 500 | DB 저장 배치 크기 |

---

## 4. 프록시 설정

### IPRoyal Residential Proxy

| 항목 | 값 |
|------|-----|
| Host | geo.iproyal.com:12321 |
| 인증 | HTTP Basic (Username:Password) |
| 동시 연결 | **무제한** |
| 과금 | 트래픽 기반 (GB당) |

### 세션 타입

**Random (매 요청 새 IP)**
```
username:password@geo.iproyal.com:12321
```

**Sticky (고정 IP 유지)**
```
username:password_session-{8자}_lifetime-{시간}@geo.iproyal.com:12321
```

### 적응형 폴백 전략

```python
# 현재 구현된 로직
1. 프록시 없이 직접 연결로 시작 (12건/s)
2. HTTP 403/429 응답 모니터링
3. 연속 5회 실패 → 프록시 모드 전환
4. 프록시로 재시도 (2.2건/s, 100% 성공)
```

---

## 5. 실측 성능 (2026-01-16)

### 크롤링 결과 (2026-01-16 최종)

| 항목 | 결과 |
|------|------|
| 목록 수집 | 25개 구별 분할 → 69,275건 (합계) |
| 중복 제거 후 | 약 51,000건 (unique IDs) |
| 상세 수집 | 51,000건 |
| 평균 속도 | 12-18건/s (30워커) |
| 프록시 | IPRoyal 30개 세션 병렬 |
| **최종 DB** | **50,995건** |

> **참고**: 구별 분할 크롤링으로 API 250페이지 제한 우회. 같은 공고가 여러 구에서 조회되어 합계(69,275) > 실제(51,000)

### 데이터 품질

| 항목 | 점수 |
|------|------|
| 필수 필드 | 100.0% |
| 위치 정보 | 99.7% |
| 서울 비율 | 99.1% |
| 최근역 | 82.2% |
| 키워드 | 93.3% |
| **종합** | **90.1%** |

---

## 6. 제목 토큰 추출

### 구현 내용

```python
# app/parsers/detail_parser.py - DetailPageParser._build_keywords()

# 모듈 레벨에서 정규식 컴파일 (성능 최적화)
_PATTERNS = {
    "whitespace": re.compile(r'\s+'),
    "non_alphanumeric": re.compile(r'[^0-9a-zA-Z가-힣+#]'),
}

_STOPWORDS = frozenset({
    "채용", "모집", "신입", "경력", "정규직", "계약직",
    "급구", "우대", "담당", "업무", "직원", "구인", ...
})

def _build_keywords(self, work_fields: List[str], title: str) -> List[str]:
    # 제목에서 토큰 추출
    title_tokens = []
    for raw_token in _PATTERNS["whitespace"].split(title):
        token = _PATTERNS["non_alphanumeric"].sub("", raw_token)
        if len(token) >= 2 and token.lower() not in _STOPWORDS:
            title_tokens.append(token)

    # work_fields + title_tokens 병합 (중복 제거)
    return list(dict.fromkeys(work_fields + title_tokens))[:7]
```

### 예시

| 제목 | 추출 키워드 |
|------|-------------|
| "[강남] JAVA 백엔드 개발자 채용" | JAVA, 백엔드, 개발자 |
| "마케팅 담당자 모집 (경력)" | 마케팅 |
| "React/Vue 프론트엔드 개발" | React, Vue, 프론트엔드, 개발 |

---

## 7. 미구현 항목 (배포 시 구현 예정)

### 7.1 Daily Sync 모드

> **상태**: 설계 완료, 구현 예정
> **목적**: 일일 증분 업데이트로 데이터 최신성 유지

#### 동작 방식

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: ID 스캔 (프록시 없음, ~5분)                        │
│     └─ 전체 목록에서 ID만 추출 (AJAX)                        │
│                                                              │
│  Phase 2: 비교                                               │
│     ├─ new_ids = current - db      (신규 공고)               │
│     └─ missing_ids = db - current  (삭제/마감 공고)          │
│                                                              │
│  Phase 3: 신규 상세 수집 (프록시 10워커, ~3분)                │
│     └─ 일평균 300-500건 예상                                 │
│                                                              │
│  Phase 4: 상태 업데이트                                      │
│     └─ missing_ids → is_active=false                         │
└─────────────────────────────────────────────────────────────┘
```

#### 구현 코드 (예정)

```python
# crawler/app/main.py

async def run_daily_sync():
    """매일 증분 동기화"""
    scraper = JobKoreaScraperV2(num_workers=10, use_proxy=False, fallback_to_proxy=True)

    try:
        await scraper.initialize()

        # Phase 1: ID 스캔 (목록만 수집, 상세 X)
        current_ids = await scraper.crawl_list()  # 전체 목록

        # Phase 2: DB와 비교
        db_ids = await get_active_job_ids_from_db()

        new_ids = current_ids - db_ids          # 신규
        missing_ids = db_ids - current_ids      # 사라진 공고

        logger.info(f"신규: {len(new_ids)}건, 사라짐: {len(missing_ids)}건")

        # Phase 3: 신규만 상세 수집
        if new_ids:
            await scraper.crawl_details(
                new_ids,
                save_callback=save_jobs,
                batch_size=100
            )

        # Phase 4: 사라진 공고 비활성화
        if missing_ids:
            await mark_jobs_inactive(
                missing_ids,
                reason="not_in_listing"
            )

        # Phase 5: 마감일 체크
        await expire_by_deadline()

    finally:
        await scraper.close()
```

#### 관련 DB 함수 (구현 필요)

```python
# crawler/app/db/firestore.py

async def get_active_job_ids_from_db() -> Set[str]:
    """활성 공고 ID 조회"""
    jobs_ref = db.collection("jobs")
    query = jobs_ref.where("is_active", "==", True).select(["id"])
    docs = await query.get()
    return {doc.id for doc in docs}

async def mark_jobs_inactive(job_ids: Set[str], reason: str):
    """공고 비활성화"""
    batch = db.batch()
    now = datetime.now()

    for job_id in job_ids:
        ref = db.collection("jobs").document(job_id)
        batch.update(ref, {
            "is_active": False,
            "inactive_reason": reason,
            "inactive_at": now,
        })

    await batch.commit()
```

### 7.2 스케줄러 설정

> **상태**: 설계 완료, 배포 시 적용
> **목적**: 자동화된 크롤링 스케줄

#### 크롤링 모드

| 모드 | 실행 시간 | 주기 | 프록시 | 예상 소요 |
|------|----------|------|--------|----------|
| `full` | 일요일 03:00 | 주 1회 | 10워커 폴백 | 40-50분 |
| `daily` | 매일 09:00 | 매일 | 10워커 폴백 | ~10분 |
| `deadline` | 매일 21:00 | 매일 | 없음 | ~1분 |

#### CLI 인터페이스 (구현 필요)

```bash
# crawler/app/main.py --mode 옵션

python app/main.py --mode full      # 전체 크롤링
python app/main.py --mode daily     # 일일 증분 (신규만)
python app/main.py --mode deadline  # 마감일 체크 (DB만)
```

#### systemd timer 설정 (배포 시)

```ini
# /etc/systemd/system/crawler-daily.timer
[Unit]
Description=Daily Crawler Sync

[Timer]
OnCalendar=*-*-* 09:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/crawler-daily.service
[Unit]
Description=Daily Crawler Sync Service

[Service]
Type=oneshot
WorkingDirectory=/opt/jobbot/crawler
ExecStart=/opt/jobbot/crawler/venv/bin/python app/main.py --mode daily
User=crawler
```

#### cron 대안

```bash
# crontab -e
0 3 * * 0 cd /opt/jobbot/crawler && ./venv/bin/python app/main.py --mode full
0 9 * * * cd /opt/jobbot/crawler && ./venv/bin/python app/main.py --mode daily
0 21 * * * cd /opt/jobbot/crawler && ./venv/bin/python app/main.py --mode deadline
```

### 7.4 전체 공고 수집 (구별 필터 크롤링)

> **상태**: ✅ 구현 완료, 운영 중
> **스크립트**: `run_crawler.py` (구별 분할 + 중복 제거 내장)
> **결과**: 51,000건 전체 수집 성공

#### 구별 공고 현황

| 구 | 코드 | 공고 수 | 전체수집 |
|-----|------|---------|----------|
| 강남구 | I010 | 16,039 | 제한 (추가분할 필요) |
| 강북구 | I150 | 6,769 | ✓ |
| 은평구 | I180 | 5,133 | ✓ |
| 양천구 | I200 | 4,900 | ✓ |
| ... | ... | ... | ✓ |
| 성동구 | I100 | 768 | ✓ |

**24개 구**: 10,000건 이하로 전체 수집 가능
**강남구**: 16,039건으로 직무 카테고리 추가 분할 필요

#### 실행 방법

```bash
cd crawler && source venv/bin/activate
python run_crawl_by_gu.py
```

#### 검증 결과 (2026-01-16)

```
3개 구 테스트 (성동구 + 송파구 + 구로구):
- 예상 합계: 2,634건
- 실제 수집: 2,229건 (고유 ID)
- 구간 중복율: 15.4%
```

#### 실측 성능 (2026-01-16)

| 항목 | 값 |
|------|------|
| 구 수 | 25개 |
| 구별 합계 | 69,275건 |
| 중복 제거 후 | **51,000건** |
| 수집 속도 | 12-18건/s (30워커) |
| **총 소요** | **약 1-2시간** |

---

### 7.3 공고 상태 관리

#### 상태 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `is_active` | boolean | 검색 대상 여부 |
| `inactive_reason` | string | 비활성화 사유 |
| `inactive_at` | timestamp | 비활성화 시각 |

#### 비활성화 사유

| 사유 | 설명 | 트리거 |
|------|------|--------|
| `not_in_listing` | 목록에서 사라짐 | Daily Sync |
| `deadline_passed` | 마감일 경과 | Deadline Check |
| `full_crawl_missing` | Full Crawl 미발견 | Full Crawl |
| `manual` | 수동 처리 | 관리자 |

---

## 8. 변경 이력

| 날짜 | 버전 | 내용 |
|------|------|------|
| 2026-01-16 | 2.2 | **대규모 리팩토링**: 파서 분리 (`DetailPageParser`), 워커 분리 (`DetailCrawlOrchestrator`), 상수 중앙화 (`CrawlerConfig`), 예외 표준화 (`exceptions.py`), 테스트 구조화 |
| 2026-01-16 | 2.1 | **서울 전체 51,000건 수집 완료** (구별 분할 + 중복 제거) |
| 2026-01-16 | 2.1 | 워커 수 확대 (10 → 30), 프록시 풀 30개 |
| 2026-01-16 | 2.1 | 상세 수집 워커-큐 패턴 리팩토링 (이슈 #013) |
| 2026-01-16 | 2.1 | 프록시 세션 lifetime 필수화 (이슈 #014) |
| 2026-01-16 | 2.0 | **API 페이지 제한 발견** (시간대별 가변: 250-500) |
| 2026-01-16 | 2.0 | 구별 크롤링 전략 설계 (전체 수집용) |
| 2026-01-16 | 2.0 | V2 운영 검증 완료 (10,000건 성공) |
| 2026-01-16 | 2.0 | 제목 토큰 추출 구현 |
| 2026-01-16 | 2.0 | 프록시 폴백 로직 검증 |
| 2026-01-15 | 2.0 | V2 Lite 초기 구현 |
| 2026-01-15 | - | AJAX 엔드포인트 발견 |
| 2026-01-14 | 1.0 | nearest_station 필드 추가 (이후 실시간 계산으로 변경) |
| 2026-01-10 | 1.0 | V1 MVP 크롤러 구현 |

---

## 부록: 트러블슈팅

### A. 페이지네이션 작동 안함 (V1 문제)

**원인**: 잡코리아 서버가 일반 `/recruit/joblist` URL의 `page` 파라미터 무시

**해결**: AJAX 엔드포인트 `/Recruit/Home/_GI_List` 사용

### B. 차단 감지

**증상**: HTTP 403/429 응답 또는 "보안문자" 페이지

**대응**:
1. 적응형 Rate Limiter가 자동으로 속도 감소
2. 연속 5회 실패 시 프록시로 자동 전환
3. 프록시 전환 후에도 실패 시 수동 확인 필요

### C. 제목/회사명 누락

**원인**: HTML 구조 변경 또는 다양한 페이지 템플릿

**대응**: 다중 소스 추출 (JSON-LD → CSS selector → meta tag → title tag)
