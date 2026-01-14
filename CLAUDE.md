# JobChat 프로젝트 유의사항

## MVP 범위 정의

### 지역 범위 (중요!)
- **서울시 한정** (25개 구만 수집)
- 크롤러 설정: `TARGET_LOCAL_CODE = "I000"` (서울 전체)
- **서울 외 지역 데이터는 저장하지 않음** (경기, 인천, 부산 등 모두 제외)
- 크롤링 시 `location_sido`가 "서울"이 아닌 공고는 필터링

### 직무 범위
| 카테고리 | 포함 직무 |
|----------|----------|
| **개발** | 백엔드, 프론트엔드, 풀스택, 앱개발, 데이터, AI, DevOps, QA 등 |
| **디자인** | UI/UX, 웹디자인, 그래픽, 영상, 제품, 브랜드 디자인 등 |
| **마케팅** | 퍼포먼스, 콘텐츠, 브랜드, CRM 마케팅 등 |
| **기획** | 서비스기획, PM, 사업기획, 전략기획 등 |
| **경영지원** | 인사, 총무, 재무회계, 법무, 비서 등 |

### MVP 제외 범위 (수집하지 않음)
- **지역**: 서울 외 모든 지역 (경기, 인천, 부산, 대구, 광주, 대전, 울산, 세종, 강원, 충북, 충남, 전북, 전남, 경북, 경남, 제주)
- **직무**: 영업, 서비스, 의료, 교육, 연구개발 등

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

**현재 해결책**: 상세 페이지 병렬 호출 (asyncio.gather) + 차단 방지 설정
- 워커 수: 1개 (기본값, 최대 3개)
- 배치 크기: 3개 (parallel_batch_size)
- 배치 간 딜레이: 1.0~2.0초
- 초당 요청: ~2개 (안전 범위)
- 예상 속도: 1,000건당 약 30~40분

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

## 아키텍처 V6 (Simple Agentic)

### V4의 한계

| 문제 | 원인 |
|------|------|
| Function Call 강제 | 항상 파라미터 추출 → 정보 부족해도 검색 실행 |
| 3-Stage 고정 파이프라인 | 유연한 대화 흐름 불가 |
| AI 의미 매칭 불필요 | DB 검색으로 충분 |

### V6 핵심 원칙

```
1. LLM = 자율적 판단자 (파라미터 추출기 X)
2. 필수 정보 3가지: 직무, 연봉, 통근 기준점
3. 정보 부족 → 질문 / 정보 충분 → search_jobs 호출
4. 검색 결과 → LLM에게 직접 전달 (50건)
5. 통근시간: 지하철 기반 계산 ($0)
```

### Simple Agentic 흐름

```
사용자: "을지로역 부근 웹 디자이너 연봉 4천"
        │
        ▼ Gemini 2.0 Flash
[LLM 자율 판단: 필수 정보 3가지 충족?]
        │
    ┌───┴───┐
    │ Yes   │ No
    ▼       ▼
search_jobs()  "어떤 직무를 찾으시나요?"
    │
    ▼
[job_search.search_jobs_with_commute()]
  1. DB 키워드 필터 (job_keywords)
  2. 연봉 필터 (salary_min)
  3. 통근시간 계산 (commute_origin → subway)
    │
    ▼
[검색 결과 50건 → LLM 전달]
    │
    ▼ LLM이 자연어 응답 생성
"을지로역 기준 통근 1시간 이내 웹 디자이너
 공고 23건을 찾았습니다. 연봉 4천만원 이상..."
```

### 구현 파일

| 파일 | 역할 |
|------|------|
| `backend/app/services/gemini.py` | Simple Agentic LLM 서비스 (Function Calling) |
| `backend/app/services/job_search.py` | DB 검색 + 통근시간 계산 |
| `backend/app/services/subway.py` | 지하철 서비스 래퍼 |
| `backend/app/services/seoul_subway_commute.py` | 지하철 통근시간 핵심 모듈 |
| `crawler/app/scrapers/jobkorea.py` | 크롤러 (nearest_station 필드 추가) |
| `scripts/migrate_nearest_station.py` | 기존 데이터 마이그레이션 |

### API 변경사항

**POST /chat**
```json
// 요청 (V6 간소화)
{"message": "강남역 부근 백엔드 연봉 5천", "conversation_id": null}

// 응답
{
  "success": true,
  "response": "강남역 기준 통근 1시간 이내...",
  "jobs": [...],
  "pagination": {"total_count": 23, "displayed": 20, "has_more": true, "remaining": 3},
  "search_params": {"job_keywords": ["백엔드"], "salary_min": 5000, "commute_origin": "강남역"},
  "conversation_id": "uuid"
}
```

**POST /chat/more** (더보기)
```json
// 요청
{"conversation_id": "uuid"}

// 응답
{"success": true, "jobs": [...], "pagination": {...}, "has_more": false}
```

### 비용 비교

| 항목 | V4 | V6 |
|------|-----|-----|
| API 비용 | $0 | **$0** |
| AI 호출 | 1회 (Function Call 강제) | **1회** (자율적 판단) |
| 유연성 | 고정 파이프라인 | **대화형 흐름** |
| 월 예상 비용 | ~$15 | **~$9** |

---

## 변경 이력

- **2026-01-13**: 아키텍처 V6 (Simple Agentic) 전환
  - gemini.py: LLM 자율 판단 로직 구현
  - job_search.py: 통근시간 기반 검색
  - 크롤러: nearest_station 필드 추가
  - 프론트엔드: 더보기 버튼, API 호출 간소화
- **2026-01-13**: 크롤러 `location_full` 필드 누락 수정, 기존 데이터 마이그레이션 (649건)
- **2026-01-13**: 아키텍처 V4 (지하철 기반, AI 위치 파싱 제거)
- **2026-01-13**: 아키텍처 V3 설계 (3-Stage Sequential Filter with Maps API)
- **2026-01-13**: 아키텍처 V2 설계 (2-Stage Hybrid) - 한계로 인해 V3로 대체
- **2026-01-12**: HTML 셀렉터 수정, MVP 필터링 개선, CORS 설정 수정
