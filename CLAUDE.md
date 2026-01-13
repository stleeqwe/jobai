# JobChat 프로젝트 유의사항

## MVP 범위 정의

### 지역 범위
- **서울 전체** (25개 구)
- 크롤러 설정: `TARGET_LOCAL_CODE = "I000"` (서울 전체)

### 직무 범위
| 카테고리 | 포함 직무 |
|----------|----------|
| **개발** | 백엔드, 프론트엔드, 풀스택, 앱개발, 데이터, AI, DevOps, QA 등 |
| **디자인** | UI/UX, 웹디자인, 그래픽, 영상, 제품, 브랜드 디자인 등 |
| **마케팅** | 퍼포먼스, 콘텐츠, 브랜드, CRM 마케팅 등 |
| **기획** | 서비스기획, PM, 사업기획, 전략기획 등 |
| **경영지원** | 인사, 총무, 재무회계, 법무, 비서 등 |

### MVP 제외 범위
- 지역: 서울 외 지역 (경기, 인천 등)
- 직무: 영업, 서비스, 의료, 교육, 연구개발 등

---

## 크롤러 관련 이슈 및 해결 방법

### 1. HTML 셀렉터 문제 (P0 - Critical)

**문제**: 잡코리아 HTML 구조 변경으로 셀렉터 불일치
- 기존: `.devloopArea` → 702개 요소 반환 (li 외 div 등 포함)
- 수정: `li.devloopArea` → 642개 정확한 공고 아이템

**영향받는 파일**: `crawler/app/scrapers/jobkorea.py`

**올바른 셀렉터**:
```python
# 목록 아이템
job_items = soup.select("li.devloopArea")
if not job_items:
    job_items = soup.select("li[data-info]")

# 제목
title_el = item.select_one(".description a .text")

# 회사명
company_el = item.select_one(".company .name a")

# 공고 ID (data-info 속성에서 추출)
data_info = item.get("data-info", "")
parts = data_info.strip().split("|")
job_id = parts[0] if parts and parts[0].isdigit() else None
```

**주의**: 잡코리아 HTML 구조가 변경될 수 있으므로 주기적으로 확인 필요

---

### 2. 크롤링 속도 문제 (P1 - Important)

**문제**: 상세 페이지 호출로 인한 극심한 속도 저하
- 3페이지 크롤링에 166분 소요 (예상: 9분)
- 페이지당 ~135개 MVP 공고 × 0.5초 딜레이

**원인**:
- 각 공고마다 상세 페이지 HTTP 요청
- 상세 페이지 파싱 시간
- Firestore 저장 시간

**현재 해결책**: `fetch_details` 파라미터 추가
```python
# 빠른 크롤링 (상세 정보 없이)
jobs = await scraper._crawl_page_with_client(client, page, 0, fetch_details=False)

# 상세 정보 포함 (느림)
jobs = await scraper._crawl_page_with_client(client, page, 0, fetch_details=True)
```

**향후 최적화 방안**:
- 상세 페이지 병렬 호출 (asyncio.gather)
- 딜레이 시간 조정 (현재 0.3~0.6초)
- 배치 크기 최적화

---

### 3. MVP 필터링 로직

**MVP 카테고리**: 개발, 디자인, 마케팅, 기획, 경영지원

**필터링 방식**: 제목 기반 키워드 매칭 → `mvp_category` 필드 저장

**주의사항**:
- `mvp_category` 필드가 Firestore에 저장됨
- MVP 범위 외 직무는 `mvp_category: "기타"`로 저장
- Backend AI 검색은 전체 공고 대상으로 의미적 매칭 수행

---

### 4. Firestore 저장 관련

**저장 방식**: `set()` with `merge=True` (upsert)
- 신규 공고: 새로 생성
- 기존 공고: 필드 병합 (crawled_at 유지)

**배치 크기**: 500건 (Firestore 제한)

**필수 필드**:
- `id`: 고유 ID (jk_XXXXXXXX 형식)
- `is_active`: 활성 상태
- `mvp_category`: MVP 카테고리
- `created_at`, `updated_at`: 타임스탬프

---

### 5. CORS 에러 해결 (P0 - 반드시 숙지)

**이 문제는 자주 발생하므로 반드시 읽고 이해할 것!**

#### 증상
- 프론트엔드에서 **"서버와 통신 중 오류가 발생했습니다"** 에러
- 백엔드 로그에 `OPTIONS /chat HTTP/1.1 400 Bad Request`

#### 원인 (왜 발생하는가?)
1. **Vite 포트 자동 변경**: Vite 개발 서버는 기본 포트(5173)가 사용 중이면 자동으로 다음 포트(5174, 5175, 5177 등)를 사용
2. **CORS 허용 목록 불일치**: 백엔드의 CORS 설정에 해당 포트가 없으면 브라우저가 요청을 차단
3. **`.env`가 `config.py`를 덮어씀**: `config.py`를 수정해도 `.env` 파일에 `ALLOWED_ORIGINS`가 있으면 `.env` 값이 우선 적용됨

#### 해결 방법

**1단계: 프론트엔드 포트 확인**
```
프론트엔드 터미널에서 확인:
➜  Local:   http://localhost:5177/   ← 이 포트 번호 확인
```

**2단계: `.env` 파일 수정 (가장 중요!)**
```bash
# backend/.env 파일을 직접 수정
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:5176,http://localhost:5177,http://localhost:5178,http://localhost:5179,http://localhost:5180,http://localhost:3000
```

**3단계: 백엔드 서버 재시작**
```bash
# .env 변경은 서버 재시작 필요
lsof -ti:8000 | xargs kill -9
cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000
```

#### 설정 우선순위 (중요!)
```
.env 파일 > config.py 기본값

따라서 .env 파일에 ALLOWED_ORIGINS가 있으면
config.py를 아무리 수정해도 적용되지 않음!
```

#### 예방책
- `.env` 파일에 포트 5173-5180까지 미리 추가해둠 (현재 적용됨)
- `config.py`에도 동일하게 설정해둠 (백업용)

#### 디버깅 명령어
```bash
# CORS 설정 확인
curl -s -X OPTIONS http://localhost:8000/chat \
  -H "Origin: http://localhost:5177" \
  -H "Access-Control-Request-Method: POST" -v 2>&1 | grep -E "(HTTP|access-control)"

# 정상이면: HTTP/1.1 200 OK + access-control-allow-origin: http://localhost:5177
# 비정상이면: HTTP/1.1 400 Bad Request
```

---

### 6. 기타 환경 설정

**포트 충돌**: 여러 서버 실행 시 포트 충돌 가능
- Frontend: 5173 → 5174 → 5175 → ... (순차 자동 시도)
- Backend: 8000 고정 (충돌 시 수동으로 기존 프로세스 종료 필요)

```bash
# 8000 포트 사용 중인 프로세스 종료
lsof -ti:8000 | xargs kill -9
```

**Firestore 인증**: `GOOGLE_APPLICATION_CREDENTIALS` 환경변수 필요

---

### 7. 테스트 시 확인 사항

1. **셀렉터 테스트**:
```python
# 정상: 600+ 개 아이템
items = soup.select("li.devloopArea")
```

2. **MVP 매칭률**: 약 20-25% (일반 공고 대비)

3. **상세 페이지 파싱 성공률**: 목표 90% 이상

4. **Firestore 저장 확인**:
```python
from app.db import get_job_stats
stats = await get_job_stats()
# total_jobs, active_jobs, last_crawl 확인
```

---

## 알려진 이슈

| 이슈 | 상태 | 비고 |
|------|------|------|
| 크롤링 속도 느림 | 미해결 | 상세페이지 병렬화 필요 |
| Python 3.9 경고 | 미해결 | Python 3.10+ 업그레이드 권장 |
| google.generativeai deprecated | 미해결 | google.genai로 마이그레이션 필요 |

---

---

## 아키텍처 V4 (3-Stage Sequential Filter with Subway)

### V3의 한계

| 문제 | 원인 |
|------|------|
| Maps API 비용 | $1.25/검색으로 비용 부담 |
| 위치 파싱 AI 호출 | 불필요한 AI 호출로 지연 발생 |
| 복수 출발지 처리 | 복잡한 로직으로 유지보수 어려움 |

### V4 핵심 원칙

```
1. 필수 정보 수집: 직무 + 연봉 (지역은 선택)
2. 직무 우선 필터: AI가 의미적으로 직무 매칭 (Stage 1)
3. 연봉 유연 필터: 회사내규/협상가능 포함 (Stage 2)
4. 지하철 기반 거리 계산: AI 호출 없이 규칙 기반 (Stage 3)
   - location_query를 그대로 SeoulSubwayCommute에 전달
   - 역명/구/동 → 좌표 변환은 모듈 내부에서 처리
```

### 3-Stage 흐름

```
[Phase 0: Function Call로 파라미터 추출]
"을지로역 부근 웹 디자이너 연봉 4천"
        │
        ▼ Gemini AI (1회 호출)
{job_type: "웹 디자이너", salary_min: 4000, location_query: "을지로역"}
        │
        ▼
[Stage 1: 직무 필터 - AI]
전체 공고 → AI가 의미적 매칭 → ~20건
        │
        ▼
[Stage 2: 연봉 필터 - DB]
salary_min >= 요청값 OR 회사내규 → ~15건
        │
        ▼
[Stage 3: 거리 필터 - 지하철 기반 (AI 호출 없음)]
subway_service.filter_jobs_by_travel_time(
    jobs=stage2_jobs,
    origin="을지로역",    ← location_query 그대로 전달
    max_minutes=60
)
        │
        ▼ SeoulSubwayCommute._parse_location() (규칙 기반)
"을지로역" → 을지로입구역 좌표 → Dijkstra → 통근시간 계산
        │
        ▼
[결과 반환]
이동시간순 정렬 + 페이지네이션
```

### 구현 파일

| 파일 | 역할 |
|------|------|
| `docs/SUBWAY_COMMUTE_MODULE.md` | 지하철 통근시간 모듈 상세 문서 |
| `crawler/CRAWLER.md` | 크롤러 유지보수 가이드 |
| `backend/app/services/gemini.py` | Function Call + 3-Stage 파이프라인 |
| `backend/app/services/job_search.py` | Stage 2 연봉 필터 |
| `backend/app/services/subway.py` | Stage 3 지하철 서비스 래퍼 |
| `backend/app/services/seoul_subway_commute.py` | 지하철 통근시간 계산 핵심 모듈 |

### 비용 비교

| 항목 | V3 (Maps API) | V4 (Subway) |
|------|---------------|-------------|
| API 비용 | $1.25/검색 | **$0** |
| AI 호출 | 2회 (Function Call + 위치 파싱) | **1회** (Function Call만) |
| 지연시간 | ~3초 | **~1초** |

---

## 변경 이력

- **2026-01-13**: 크롤러 `location_full` 필드 누락 수정, 기존 데이터 마이그레이션 (649건)
- **2026-01-13**: 아키텍처 V4 (지하철 기반, AI 위치 파싱 제거)
- **2026-01-13**: 아키텍처 V3 설계 (3-Stage Sequential Filter with Maps API)
- **2026-01-13**: 아키텍처 V2 설계 (2-Stage Hybrid) - 한계로 인해 V3로 대체
- **2026-01-12**: HTML 셀렉터 수정, MVP 필터링 개선, CORS 설정 수정
