# JobChat 프로젝트 유의사항

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

**MVP 카테고리**: 개발, 디자인, 마케팅, 기획

**필터링 방식**: 제목 기반 키워드 매칭
```python
# 키워드 예시
MVP_JOB_FILTERS = {
    "개발": ["개발자", "developer", "engineer", "백엔드", "프론트엔드", ...],
    "디자인": ["디자이너", "designer", "ui", "ux", ...],
    "마케팅": ["마케터", "marketing", "광고", "콘텐츠", ...],
    "기획": ["기획자", "pm", "po", "서비스기획", ...],
}
```

**주의사항**:
- 제목에 키워드가 없으면 필터링됨
- `mvp_category` 필드가 Firestore에 저장됨
- Backend 검색 시 `mvp_category` 우선 매칭

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

## 아키텍처 V3 (3-Stage Sequential Filter with Maps API)

### V2의 한계

| 문제 | 원인 |
|------|------|
| 위치 필터 실패 | "을지로역" → "중구" 수동 매핑 불가능 |
| 직무 매칭 실패 | AI가 "프론트 앱 개발자"와 "웹디자이너" 혼동 |
| 연봉 필터 실패 | 대부분 공고가 `salary_min=None` |
| 불완전한 검색 | 필수 조건 없이도 검색 시도 |

### V3 핵심 원칙

```
1. 필수 정보 수집: 직무, 연봉, 지역 - 3가지 없으면 검색 안함
2. 직무 우선 필터: AI가 의미적으로 직무 매칭 (Stage 1)
3. 연봉 유연 필터: 회사내규/협상가능 포함 (Stage 2)
4. Maps API 거리 계산: 실제 이동시간 기반 필터링 (Stage 3)
```

### 3-Stage 흐름

```
[Phase 0: 필수 정보 수집]
직무 + 연봉 + 지역 → 3가지 모두 필수
        │
        ▼
[Stage 1: 직무 필터 - AI]
전체 공고 → AI가 의미적 매칭 → ~100건
        │
        ▼
[Stage 2: 연봉 필터 - DB]
salary_min >= 요청값 OR NULL (회사내규) → ~80건
        │
        ▼
[Stage 3: 지역 필터 - Maps API]
Google Maps Distance Matrix API로 실제 이동시간 계산
"을지로역에서 30분 이내" → 주소 없는 공고 제외 → ~20건
        │
        ▼
[결과 반환]
이동시간순 정렬 + 페이지네이션
```

### 구현 파일

| 파일 | 역할 |
|------|------|
| `docs/ARCHITECTURE_V3.md` | 상세 설계 문서 |
| `backend/app/services/gemini.py` | Phase 0 가이드 + Stage 1 직무 필터 |
| `backend/app/services/job_search.py` | Stage 2 연봉 필터 |
| `backend/app/services/maps.py` | Stage 3 Maps API 연동 (신규) |
| `backend/app/config.py` | GOOGLE_MAPS_API_KEY 추가 |

### 환경 설정

```bash
# backend/.env 에 추가
GOOGLE_MAPS_API_KEY=your_api_key_here
```

---

## 변경 이력

- **2026-01-13**: 아키텍처 V3 설계 (3-Stage Sequential Filter with Maps API)
- **2026-01-13**: 아키텍처 V2 설계 (2-Stage Hybrid) - 한계로 인해 V3로 대체
- **2026-01-12**: HTML 셀렉터 수정, MVP 필터링 개선, CORS 설정 수정
