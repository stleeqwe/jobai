# 크롤러 업데이트 계획

> 작성일: 2026-01-16
> 상태: 승인됨

## 1. 개요

### 목표
- 프록시 기반 안정적 크롤링 체계 구축
- 일일 증분 업데이트로 데이터 최신성 유지
- 제목 키워드 추출로 검색 품질 향상

### 주요 변경사항
1. **프록시 전략**: 상세 페이지 수집 시 프록시 10워커 기본 적용
2. **스케줄링**: 주 1회 Full + 매일 Sync 구조
3. **데이터 품질**: 제목 토큰을 job_keywords에 추가

---

## 2. 아키텍처

### 크롤링 모드

| 모드 | 실행 시간 | 주기 | 프록시 | 예상 소요 |
|-----|---------|-----|-------|---------|
| `full` | 일요일 03:00 | 주 1회 | 10워커 | 40-50분 |
| `daily` | 매일 09:00 | 매일 | 10워커 (신규만) | ~10분 |
| `deadline` | 매일 21:00 | 매일 | 없음 | ~1분 |

### 데이터 흐름

```
[Full Crawl - 주 1회]
┌─────────────────────────────────────────────────────────────┐
│ 1. 25개 구 목록 조회 (프록시 없음)                            │
│    └─ AJAX: /Recruit/Home/_GI_List?local=I0XX               │
│ 2. 전체 ID 수집 (~60,000건)                                  │
│ 3. DB 비교 → 신규/변경 ID 식별                               │
│ 4. 상세 페이지 수집 (프록시 10워커)                           │
│    └─ 세션 분리: _session-workerXX_lifetime-10m             │
│ 5. DB 저장 + 만료 공고 비활성화                              │
└─────────────────────────────────────────────────────────────┘

[Daily Sync - 매일]
┌─────────────────────────────────────────────────────────────┐
│ Phase 1: ID 스캔 (프록시 없음, ~5분)                         │
│    └─ 전체 목록에서 ID만 추출                                │
│ Phase 2: 비교                                               │
│    ├─ new_ids = current - db      (신규)                    │
│    └─ missing_ids = db - current  (삭제/마감)               │
│ Phase 3: 신규 상세 수집 (프록시 10워커, ~3분)                 │
│    └─ 일평균 300-500건 예상                                  │
│ Phase 4: 상태 업데이트                                       │
│    └─ missing_ids → is_active=false                         │
└─────────────────────────────────────────────────────────────┘

[Deadline Check - 매일 밤]
┌─────────────────────────────────────────────────────────────┐
│ • DB에서 deadline < today인 활성 공고 조회                   │
│ • is_active=false 처리                                      │
│ • 네트워크 요청 없음                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 프록시 설정

### IPRoyal 구성

| 항목 | 값 |
|-----|---|
| Host | geo.iproyal.com:12321 |
| 인증 | HTTP Basic (Username:Password) |
| 동시 연결 | **무제한** |
| 세션 수명 | 1초 ~ 7일 |

### 세션 설정

**워커별 고정 IP (Sticky Session):**
```
username:password_session-worker01_lifetime-10m@geo.iproyal.com:12321
username:password_session-worker02_lifetime-10m@geo.iproyal.com:12321
...
username:password_session-worker10_lifetime-10m@geo.iproyal.com:12321
```

**랜덤 IP (Random Rotation):**
```
username:password@geo.iproyal.com:12321
```

### 워커 설정

| 단계 | 워커 수 | 세션 타입 | 요청 간격 |
|-----|--------|---------|---------|
| 목록 수집 | 1 | Random | 200ms |
| 상세 수집 | 10 | Sticky (10분) | 300-500ms |

---

## 4. 코드 변경 사항

### 4.1 제목 토큰 추출 (P1)

**파일:** `crawler/app/scrapers/jobkorea.py`

```python
def _extract_title_tokens(title: str) -> List[str]:
    """제목에서 직무 관련 토큰 추출"""
    import re
    cleaned = re.sub(r'[^\w\s가-힣]', ' ', title)
    tokens = cleaned.split()
    stopwords = {'채용', '모집', '신입', '경력', '정규직', '계약직', '급구', '상시', '대량'}
    return [t for t in tokens if len(t) >= 2 and t not in stopwords][:5]

# job_keywords 병합
merged_keywords = list(dict.fromkeys(job_types + title_tokens))[:7]
```

### 4.2 Daily Sync 모드 추가 (P0)

**파일:** `crawler/app/main.py`

```python
async def run_daily_sync():
    """매일 증분 동기화"""
    scraper = JobKoreaScraperV2(num_workers=10, use_proxy=True)

    # Phase 1: ID 스캔
    current_ids = await scraper.scan_all_ids()
    db_ids = await get_active_job_ids_from_db()

    new_ids = current_ids - db_ids
    missing_ids = db_ids - current_ids

    # Phase 2: 신규 상세 수집
    if new_ids:
        await scraper.crawl_details(new_ids, save_callback=save_to_firestore)

    # Phase 3: 사라진 공고 비활성화
    if missing_ids:
        await mark_jobs_inactive(missing_ids)

    # Phase 4: 마감일 체크
    await check_expired_deadlines()
```

### 4.3 프록시 워커 풀 (P0)

**파일:** `crawler/app/core/session_manager.py`

```python
def get_proxy_url_with_session(worker_id: int, lifetime: str = "10m") -> str:
    """워커별 세션 분리된 프록시 URL"""
    session_id = f"worker{worker_id:02d}"
    return (
        f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}"
        f"_session-{session_id}_lifetime-{lifetime}"
        f"@{PROXY_HOST}:{PROXY_PORT}"
    )
```

---

## 5. 공고 상태 관리

### 상태 정의

| 필드 | 타입 | 설명 |
|-----|-----|-----|
| `is_active` | boolean | 검색 대상 여부 |
| `inactive_reason` | string | 비활성화 사유 |
| `inactive_at` | timestamp | 비활성화 시각 |

### 비활성화 사유

| 사유 | 설명 | 트리거 |
|-----|------|-------|
| `not_in_listing` | 목록에서 사라짐 | Daily Sync |
| `deadline_passed` | 마감일 경과 | Deadline Check |
| `full_crawl_missing` | Full Crawl 미발견 | Full Crawl |
| `manual` | 수동 처리 | 관리자 |

---

## 6. 테스트 계획

### 단위 테스트

| 테스트 | 파일 | 검증 내용 |
|-------|-----|---------|
| 제목 토큰 추출 | `test_title_tokens.py` | 불용어 제거, 토큰화 |
| 프록시 세션 | `test_proxy_session.py` | 워커별 IP 분리 |
| Daily Sync | `test_daily_sync.py` | ID 비교 로직 |

### 통합 테스트

```bash
# 1. 프록시 연결 테스트 (10워커)
python -m pytest test_proxy_parallel.py -v

# 2. Daily Sync 드라이런
python app/main.py --mode daily --dry-run

# 3. 제목 토큰 반영 확인
python test_e2e_quality.py
```

---

## 7. 롤백 계획

### 실패 시 대응

| 상황 | 대응 |
|-----|------|
| 프록시 차단 | 워커 수 감소 (10→5) |
| 500p 초과 | 구단위 분할 활성화 |
| DB 오류 | 배치 크기 감소 |

### 롤백 명령어

```bash
# 이전 버전으로 롤백
git checkout HEAD~1 -- crawler/app/

# 서비스 재시작
systemctl restart crawler-daily
```

---

## 8. 일정

| 단계 | 작업 | 예상 소요 |
|-----|------|---------|
| 1 | 문서화 완료 | 완료 |
| 2 | 코드 수정 | 1시간 |
| 3 | 테스트 | 30분 |
| 4 | 배포 | - |

---

## 변경 이력

| 날짜 | 버전 | 내용 |
|-----|-----|-----|
| 2026-01-16 | 1.0 | 초안 작성 |
