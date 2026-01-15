# Project: JobChat

> 서울 지역 취업 공고를 AI 기반으로 검색하는 채팅 서비스

## Commands

### Backend
- `cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000`: 백엔드 개발 서버
- `lsof -ti:8000 | xargs kill -9`: 8000 포트 강제 종료
- `cd backend && python -m pytest`: 백엔드 테스트
- `curl http://localhost:8000/model-info`: Gemini 모델 확인

### Frontend
- `cd frontend && npm run dev`: 프론트엔드 개발 서버 (Vite)
- `cd frontend && npm run build`: 프로덕션 빌드
- `cd frontend && npm run lint`: ESLint 검사

### Crawler
- `cd crawler && source venv/bin/activate && python crawl_seoul.py`: 서울 공고 크롤링
- `cd crawler && python -m pytest test_*.py`: 크롤러 테스트

## Architecture

```
/
├── backend/                 # FastAPI 백엔드
│   ├── app/
│   │   ├── main.py         # 엔트리포인트, API 라우터
│   │   ├── config.py       # 환경설정 (Pydantic Settings)
│   │   ├── db.py           # Firestore 연동
│   │   └── services/
│   │       ├── gemini.py   # Gemini API (Simple Agentic)
│   │       ├── job_search.py
│   │       └── seoul_subway_commute.py
│   └── .env                # 환경변수 (GEMINI_API_KEY, ALLOWED_ORIGINS 등)
├── frontend/               # React + Vite + Tailwind
│   └── src/
│       ├── App.tsx
│       └── components/
├── crawler/                # 잡코리아 크롤러
│   └── app/scrapers/
│       └── jobkorea.py     # 핵심 스크래퍼
└── scripts/                # 유틸리티 스크립트
```

## Code Style

### Python (Backend, Crawler)
- Python 3.10+ 타입 힌트 사용
- async/await 패턴 (FastAPI, httpx)
- Pydantic 모델로 데이터 검증

### TypeScript (Frontend)
- 함수형 컴포넌트 + React Hooks
- Tailwind CSS (inline style 금지)

### 공통
- 환경변수는 `.env` 파일에 정의 (절대 커밋 금지)

## Git

- 브랜치: `feat/`, `fix/`, `chore/` 접두사
- 커밋: 한국어 또는 영어, 변경 내용 명확히
- main 브랜치 직접 푸시 허용 (개인 프로젝트)

## Testing

- **Backend**: `cd backend && python -m pytest`
- **Crawler**: `cd crawler && python -m pytest test_*.py`
- 크롤러 셀렉터 변경 시 `test_e2e_quality.py` 실행

## Environment

- **Python**: 3.10+
- **Node.js**: 18+
- **가상환경**: `backend/venv`, `crawler/venv`
- **Firestore**: `GOOGLE_APPLICATION_CREDENTIALS` 환경변수 필요

---

## IMPORTANT

### 1. MVP 범위 - 서울시 한정
- **서울시만** 수집 (25개 구)
- 크롤러: `TARGET_LOCAL_CODE = "I000"`
- `location_sido`가 "서울"이 아닌 공고는 저장하지 않음

### 2. 설정 파일 우선순위
```
.env 파일 > config.py 기본값
```
`config.py`를 수정해도 `.env`에 같은 키가 있으면 `.env` 값이 적용됨!

### 3. CORS 에러 해결 (자주 발생!)

**증상**: 프론트엔드 "서버와 통신 중 오류", 백엔드 `OPTIONS 400 Bad Request`

**원인**: Vite 포트 자동 변경 (5173 → 5174 → ...) + CORS 허용 목록 불일치

**진단:**
```bash
curl -s -X OPTIONS http://localhost:8000/chat \
  -H "Origin: http://localhost:<PORT>" \
  -H "Access-Control-Request-Method: POST" -v 2>&1 | grep -E "(HTTP|access-control)"
```
- 성공: `HTTP/1.1 200 OK` + `access-control-allow-origin`
- 실패: `HTTP/1.1 400 Bad Request`

**해결:**
1. `backend/.env`의 `ALLOWED_ORIGINS`에 해당 포트 추가
2. 백엔드 서버 재시작: `lsof -ti:8000 | xargs kill -9 && cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000`

**예방**: 5173-5180 포트 미리 등록됨

### 4. Gemini API 설정

**현재 설정:**
- 모델: `gemini-3-flash-preview`
- SDK: `google.genai` v1.47.0
- Thinking: `thinking_budget=8192`

**SDK 주의 (중요!):**
```python
# CORRECT
from google import genai
from google.genai import types

# WRONG (deprecated)
from google.generativeai import ...
```

**모델 변경 시:**
1. `backend/.env`의 `GEMINI_MODEL` 수정
2. 서버 재시작
3. `curl http://localhost:8000/model-info`로 확인

### 5. 크롤러 셀렉터 (HTML 구조 변경 시)

**현재 유효한 셀렉터 (2026-01):**
```python
# 목록 - 반드시 "li.devloopArea" 사용 (.devloopArea는 div 포함됨)
job_items = soup.select("li.devloopArea")

# 제목, 회사명
title_el = item.select_one(".description a .text")
company_el = item.select_one(".company .name a")
```

잡코리아 HTML 변경 시 `crawler/app/scrapers/jobkorea.py` 수정 필요.
상세 유지보수 가이드: `.claude/skills/crawler-maintenance/SKILL.md`

### 6. 크롤러 스케줄 및 프록시 설정

> **상세 계획:** `crawler/docs/CRAWLER_UPDATE_PLAN.md`

**크롤링 모드:**
| 모드 | 실행 시간 | 주기 | 프록시 | 용도 |
|-----|---------|-----|-------|-----|
| `full` | 일요일 03:00 | 주 1회 | 10워커 | 전체 동기화 |
| `daily` | 매일 09:00 | 매일 | 10워커 | 신규/삭제 감지 |
| `deadline` | 매일 21:00 | 매일 | 없음 | 마감일 체크 |

**실행 명령어:**
```bash
cd crawler && source venv/bin/activate
python app/main.py --mode full      # 전체 크롤링
python app/main.py --mode daily     # 일일 증분
python app/main.py --mode deadline  # 마감일 체크
```

**IPRoyal 프록시:**
- Host: `geo.iproyal.com:12321`
- 동시 연결: **무제한**
- 세션 형식: `_session-{8자}_lifetime-{시간}` (Sticky)
- 문서: `crawler/docs/IPROYAL_PROXY.md`

**관련 파일:**
- `crawler/app/core/session_manager.py` - 프록시 세션 관리
- `crawler/app/core/ajax_client.py` - 적응형 rate limiter
- `crawler/app/scrapers/jobkorea_v2.py` - V2 스크래퍼

**완료 항목:**
- [x] V2 크롤러 기본 동작 검증
- [x] 10,000건+ 크롤링 성공
- [x] 프록시 10워커 구조 설계
- [ ] Daily Sync 모드 구현
- [ ] 제목 토큰 추출 구현

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/chat` | 채팅 메시지 |
| POST | `/chat/more` | 추가 결과 조회 |
| GET | `/model-info` | Gemini 설정 확인 |
| GET | `/health` | 헬스체크 |

---

## 아키텍처 V6 (Simple Agentic)

```
사용자 메시지 → Gemini LLM (자율 판단)
                    │
          ┌─────────┴─────────┐
          │                   │
    정보 부족 시           정보 충분 시
    "어떤 직무를?"        search_jobs() 호출
                                │
                    DB 검색 + 통근시간 계산
                                │
                    결과 50건 → LLM → 응답
```

**필수 정보 3가지**: 직무, 연봉, 통근 기준점
