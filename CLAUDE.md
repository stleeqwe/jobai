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

### 5. 크롤러 V2

> **상세 문서**: `crawler/docs/CRAWLER.md`

**현재 상태 (2026-01-16 검증 완료):**

| 항목 | 값 |
|------|-----|
| 버전 | V2 Lite (httpx + AJAX) |
| 서울 전체 공고 | ~64,000건 |
| 실측 수집량 | 10,000건/회 |
| 수집 속도 | 4.4건/s (10워커) |
| 데이터 품질 | 90.1% |

**실행 명령어:**
```bash
cd crawler && source venv/bin/activate
python run_crawl_500.py       # 500페이지 크롤링 (10,000건)
python test_e2e_quality.py    # 데이터 품질 검증
```

**핵심 파일:**
- `crawler/app/scrapers/jobkorea_v2.py` - V2 메인 스크래퍼
- `crawler/app/core/session_manager.py` - 세션/프록시 관리
- `crawler/app/core/ajax_client.py` - AJAX 클라이언트

**완료 항목:**
- [x] V2 크롤러 운영 검증 (10,000건 성공)
- [x] 프록시 폴백 로직 구현
- [x] 제목 토큰 추출 → job_keywords 반영
- [x] 데이터 품질 90%+ 달성

**미구현 (배포 시 구현 예정):**
- [ ] Daily Sync 모드 (일일 증분 업데이트)
- [ ] 스케줄러 설정 (systemd timer / cron)
- 상세: `crawler/docs/CRAWLER.md` 섹션 7 참조

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
