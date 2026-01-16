# Project: JobBot

> 서울 지역 취업 공고를 AI 기반으로 검색하는 채팅 서비스

---

## Agent Structure

이 프로젝트는 Claude Code 네이티브 에이전트 시스템을 사용합니다.

### 에이전트 구성

| 영역 | 담당 | 역할 | 비고 |
|------|------|------|------|
| **Backend** | Claude | 읽기/분석/수정 | `.claude/agents/backend-dev.md` |
| **Frontend** | Claude | 읽기/분석/수정 | `.claude/agents/frontend-dev.md` |
| **Crawler** | Claude + Codex | Claude: 읽기/분석, Codex: 수정 | 협업 모델 (섹션 6 참조) |
| **Tests** | Codex | 테스트 실행/이슈 기록 | `tests/AGENTS.md` |
| **Deploy** | Claude + Codex | Claude: 계획 수립, Codex: 실행 | 협업 모델 (섹션 7 참조) |

### 협업 모델 요약

```
Frontend/Backend 문제 → Claude 단독 처리
         ↓
문제가 Crawler까지 연결 → Claude 전방위 분석 (읽기만)
         ↓
수정 필요 시 → Codex에 협업 요청 (분석 공유 + 추가 검토)
         ↓
Codex 자체 분석 → 공동 수정 계획 → Codex 수정 실행
```

### 디렉토리 구조

```
.claude/
├── agents/
│   ├── backend-dev.md      # 백엔드 Claude 에이전트
│   └── frontend-dev.md     # 프론트엔드 Claude 에이전트
├── rules/
│   ├── backend.md          # backend/**/*.py 작업 시 규칙
│   └── frontend.md         # frontend/**/*.tsx 작업 시 규칙
└── skills/
    └── crawler-maintenance/ # 크롤러 유지보수 스킬

crawler/AGENTS.md           # Codex 크롤러 에이전트
tests/AGENTS.md             # Codex 테스트 에이전트
deploy/AGENTS.md            # Codex 배포 에이전트
```

### 규칙 적용

- **Rules** (`.claude/rules/`): 경로 패턴에 따라 자동 적용
  - `backend/**/*.py` → `backend.md` 규칙 적용
  - `frontend/**/*.tsx` → `frontend.md` 규칙 적용
- **Agents**: Task 호출 시 전문 에이전트 사용 가능
- **Crawler**: Claude는 읽기/분석만, 수정은 Codex 협업 요청

---

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
- `cd crawler && source venv/bin/activate && python run_crawler.py`: 전체 크롤링
- `cd crawler && python run_crawler.py --skip-existing`: 증분 크롤링 (신규만)
- `cd crawler && python test_e2e_quality.py`: 데이터 품질 검증

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
│   ├── run_crawler.py      # 메인 크롤러 스크립트
│   └── app/scrapers/
│       └── jobkorea_v2.py  # V2 스크래퍼 (AJAX 기반)
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

> **상세 문서**: `docs/E2E_TEST_PLAN.md`
> **테스트 에이전트**: `tests/AGENTS.md` (Codex)

### 테스트 디렉토리 구조

```
tests/                           # 테스트 전용 디렉토리
├── AGENTS.md                    # Codex 테스트 에이전트 지침
├── e2e/                         # E2E 테스트
│   ├── conftest.py              # pytest fixtures
│   ├── test_basic_search.py     # TC-001~010: 기본 검색
│   ├── test_conversation.py     # TC-020~030: 연속 대화
│   ├── test_response_quality.py # TC-040~050: AI 응답 품질
│   ├── test_edge_cases.py       # TC-060~070: 엣지 케이스
│   └── test_performance.py      # TC-090~095: 성능
├── fixtures/                    # 테스트 데이터
├── reports/                     # 테스트 결과 리포트
├── scripts/                     # 자동화 스크립트
│   └── run_tests.py             # 테스트 실행 스크립트
└── .codex/
    ├── issues/                  # 발견된 이슈 기록
    └── skills/                  # Codex Skills
        ├── run-all-tests/
        ├── test-basic/
        ├── test-conversation/
        └── generate-report/
```

### 테스트 명령어

```bash
# 자동화 스크립트 (권장)
python tests/scripts/run_tests.py                  # 전체 테스트
python tests/scripts/run_tests.py -c basic         # 기본 검색만
python tests/scripts/run_tests.py -c conversation  # 대화 테스트만
python tests/scripts/run_tests.py --fast           # 느린 테스트 제외
python tests/scripts/run_tests.py --report         # 리포트 생성

# pytest 직접 실행
python -m pytest tests/e2e/ -v
python -m pytest tests/e2e/test_basic_search.py -v

# 크롤러 테스트
cd crawler && python test_e2e_quality.py
```

### 테스트 에이전트 (Codex)

**테스트 관련 작업은 Codex 에이전트가 수행합니다.**

| Skill | 트리거 | 설명 |
|-------|--------|------|
| `/run-all-tests` | 전체 테스트 | E2E 전체 실행 + 리포트 |
| `/test-basic` | 기본 검색 | TC-001~010 |
| `/test-conversation` | 연속 대화 | TC-020~030 |
| `/test-quality` | 응답 품질 | TC-040~050 |
| `/generate-report` | 리포트 생성 | HTML/JSON 리포트 |
| `/analyze-failures` | 실패 분석 | 원인 분석 + 이슈 기록 |

### 합격 기준

| 항목 | 설명 | 기준 |
|------|------|------|
| 전체 통과율 | 전체 테스트 | ≥ 80% |
| AI 판단 | search_jobs/filter_results 선택 | 90%+ |
| 컨텍스트 | 연속 대화 조건 유지 | 유실 0건 |
| 성능 | 첫 응답 시간 | < 5초 |

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

**현재 상태 (2026-01-16 업데이트):**

| 항목 | 값 |
|------|-----|
| 버전 | V2 (httpx + AJAX + 구별 분할) |
| 서울 전체 공고 | ~51,000건 (구별 중복 제거 후) |
| 수집 가능량 | ~51,000건 전체 (구별 분할로 API 제한 우회) |
| 수집 속도 | 12-18건/s (30워커, 프록시 풀 30개) |
| 데이터 품질 | 71.2% (필수 필드 100%) |

#### ⚠️ 크롤러 실행 전 필수 확인사항

**절대 임의로 진행하지 말 것! 반드시 사용자에게 확인 후 진행.**

1. **프록시 설정 확인** (필수):
   ```bash
   cat crawler/.env | grep PROXY_
   ```
   - `PROXY_HOST`, `PROXY_PORT`, `PROXY_USERNAME`, `PROXY_PASSWORD` 모두 설정되어야 함
   - 누락 시 → 사용자에게 설정 요청 (임의로 프록시 없이 진행 금지!)

2. **설정 누락/오류 시 대응**:
   - ❌ 임의로 대체 모드로 진행
   - ✅ 즉시 중단하고 사용자에게 보고 및 확인 요청

3. **크롤링 중 모니터링 필수**:
   - 속도 (목표: 10건/s 이상)
   - 차단/레이트리밋 (403, 429)
   - 404 스킵 비율
   - 프록시 정상 동작 여부

4. **이상 발견 시**:
   - 즉시 사용자에게 보고
   - 조치 방안 제시
   - 사용자 승인 후 진행

**실행 명령어:**
```bash
cd crawler && source venv/bin/activate
python run_crawler.py                 # 전체 크롤링 (64,000건)
python run_crawler.py --skip-existing # 증분 크롤링 (신규만)
python run_crawler.py --list-only     # 목록만 수집
python test_e2e_quality.py            # 데이터 품질 검증
```

**핵심 파일:**
- `crawler/run_crawler.py` - 메인 크롤러 (구별 분할 + 프록시 풀)
- `crawler/app/scrapers/jobkorea_v2.py` - V2 스크래퍼 (오케스트레이션)
- `crawler/app/parsers/detail_parser.py` - 상세 페이지 파서 (JSON-LD/CSS/정규식)
- `crawler/app/workers/detail_worker.py` - 상세 크롤링 오케스트레이터
- `crawler/app/config.py` - 크롤러 상수 중앙화
- `crawler/app/core/session_manager.py` - 세션/프록시 관리
- `crawler/app/core/ajax_client.py` - AJAX 클라이언트
- `crawler/app/db/firestore.py` - DB 저장 (skip 로직 포함)

**완료 항목:**
- [x] V2 크롤러 운영 검증 (64,000건 전수 수집)
- [x] 구별 분할 크롤링 (API 250페이지 제한 우회)
- [x] 강남구 추가 분할 (jobtype+career 조합)
- [x] 프록시 풀 모드 (10세션 병렬)
- [x] 증분 크롤링 (--skip-existing)
- [x] 데이터 품질 90%+ 달성
- [x] 크롤러 파일 통합 정리

**미구현 (배포 시 구현 예정):**
- [ ] 스케줄러 설정 (systemd timer / cron)
- 상세: `crawler/docs/CRAWLER.md` 참조

### 6. 크롤러 작업: Claude-Codex 협업

**Claude는 분석, Codex는 수정. 단, 단순 지시가 아닌 공동 분석 협업.**

#### 협업 모델

```
문제 발생 → Claude 전방위 분석 (프론트→백엔드→크롤러)
         → 원인 가설 수립
         → Codex에 협업 요청 (분석 공유 + 추가 검토 요청)
         → Codex 자체 분석 수행
         → 공동 수정 계획 도출
         → Codex 수정 실행 + 검증
```

#### 역할 분담

| 역할 | Claude | Codex |
|------|--------|-------|
| 크롤러 코드 읽기/분석 | ✓ | ✓ |
| 전방위 원인 추적 | ✓ | |
| 가설 수립 및 공유 | ✓ | |
| 추가 분석 및 검증 | | ✓ |
| 수정 계획 도출 | 협업 | 협업 |
| 코드 수정 | | ✓ |
| 이슈 기록 | | ✓ |
| 테스트 실행 | | ✓ |

#### Claude의 크롤러 분석 범위

Claude는 다음을 **읽고 분석**할 수 있음 (수정은 Codex):

- `crawler/app/scrapers/` - 스크래핑 로직
- `crawler/app/parsers/` - 상세 페이지 파싱 (JSON-LD/CSS/정규식)
- `crawler/app/workers/` - 크롤링 오케스트레이터
- `crawler/app/normalizers/` - 데이터 정규화
- `crawler/app/db/` - DB 저장 로직
- `crawler/app/core/` - 세션/프록시/Rate Limiter
- `crawler/app/config.py` - 크롤러 상수
- `crawler/app/exceptions.py` - 커스텀 예외
- `crawler/.codex/issues/` - 기존 이슈 히스토리

#### Codex 협업 요청 형식

```
[Codex 협업 요청]

## 1. 상황
(문제 증상, 발생 경위)

## 2. Claude 분석 결과
- 추적 경로: 프론트 → 백엔드 → 크롤러
- 의심 원인: (구체적 파일:라인, 로직 설명)
- 가설: "~한 이유로 ~가 발생한 것 같다"

## 3. Codex 추가 검토 요청
- [ ] 위 가설이 맞는지 검증해줘
- [ ] 다른 원인이 있을 수 있는지 확인해줘
- [ ] 관련 기존 이슈 있는지 조회해줘

## 4. 참고
- 기존 이슈 검색 키워드: "location", "파싱" 등
- 관련 문서: crawler/docs/CRAWLER.md

## 5. 기대 결과
- 원인 확정 후 수정 계획 공유
- 수정 완료 후 품질 검증 (90%+ 유지)
```

#### Codex 절대 규칙 (AGENTS.md)

```
⚠️ 코드 수정 전 반드시 이슈 먼저!

협업 요청 수신 → 자체 분석 → 기존 이슈 조회 → 이슈 생성
              → 수정 내용 먼저 기록 → 코드 수정 → 검증 → 이슈 닫기
```

#### 이슈 관리 구조

```
crawler/.codex/issues/
├── _TEMPLATE.md          # 이슈 템플릿
├── 001_*.md              # 기존 이슈들
└── NNN_이슈제목.md       # 새 이슈
```

#### 크롤러 핵심 파일

| 파일 | 역할 | 수정 시 주의 |
|------|------|-------------|
| `app/scrapers/jobkorea_v2.py` | V2 메인 크롤러 (오케스트레이션) | 이슈 필수, 테스트 필수 |
| `app/parsers/detail_parser.py` | 상세 페이지 파싱 (JSON-LD/CSS/정규식) | 셀렉터/패턴 변경 주의 |
| `app/workers/detail_worker.py` | 상세 크롤링 오케스트레이터 | 병렬 로직 주의 |
| `app/config.py` | 크롤러 상수 (URL, 타임아웃) | 관련 파일 영향 확인 |
| `app/exceptions.py` | 커스텀 예외 | 에러 핸들링 영향 확인 |
| `app/core/session_manager.py` | 세션/프록시 관리 | 인증 로직 주의 |
| `app/core/ajax_client.py` | AJAX + Rate Limiter | API 변경 시 이슈 |
| `app/normalizers/*.py` | 데이터 정규화 | 매핑 추가 시 이슈 |
| `app/db/firestore.py` | DB 저장 | 필드 변경 시 이슈 |

#### 검증 명령어

```bash
cd crawler && source venv/bin/activate

# 품질 검증 (필수)
python test_e2e_quality.py

# 단위 테스트
python -m pytest test_v2_crawler.py -v

# 특정 필드 빈 값 확인
python -c "
from app.db.firestore import get_db
db = get_db()
field = 'location_full'
empty = list(db.collection('jobs').where(field, '==', '').limit(10).stream())
print(f'빈 {field}: {len(empty)}건')
"
```

#### (레거시) 단순 작업 요청 형식

단순 버그 수정 등 협업 분석이 불필요한 경우:

```
[Codex 작업 요청]

## 작업 유형
- [ ] 버그 수정
- [ ] 기능 추가
- [ ] 셀렉터 업데이트
- [ ] 정규화 로직 수정

## 상세 내용
- 문제: (발생 증상)
- 원인: (분석 결과)
- 대상 파일: crawler/app/scrapers/jobkorea_v2.py
- 수정 내용: (구체적인 변경 사항)

## 참고
- 기존 이슈 검색 키워드: "location", "파싱" 등
- 관련 문서: crawler/docs/CRAWLER.md

## 검증
- python test_e2e_quality.py
- 기대 결과: 품질 점수 90%+ 유지
```

#### 자주 발생하는 문제 패턴

| 문제 | 검색 키워드 | 주요 원인 |
|------|-------------|-----------|
| 빈 필드 | `empty`, `missing`, `빈` | JSON-LD/CSS 구조 변경 |
| 파싱 실패 | `selector`, `셀렉터`, `parse` | 잡코리아 HTML 변경 |
| 차단 | `block`, `403`, `429` | Rate Limit, IP 차단 |

#### 문서 참조

- **기술 상세**: `crawler/docs/CRAWLER.md`
- **에이전트 규칙**: `crawler/AGENTS.md`
- **프록시 설정**: `crawler/docs/IPROYAL_PROXY.md`

### 7. 배포 작업: Claude-Codex 협업

**Claude는 계획 수립, Codex는 실행. GCP Cloud Run 기반.**

#### 협업 모델

```
배포 요청 → Claude 배포 전략 분석
         → 인프라 계획 수립 (서비스, 환경변수, 리전 등)
         → Codex에 실행 요청 (복사-붙여넣기 형식)
         → Codex 사전 체크 + 이슈 생성
         → Codex 배포 실행 + 검증
         → 결과 공유
```

#### 역할 분담

| 역할 | Claude | Codex |
|------|--------|-------|
| 배포 전략 분석 | ✓ | |
| 인프라 계획 수립 | ✓ | |
| 리스크 평가 | ✓ | |
| 계획 검토 및 검증 | | ✓ |
| Dockerfile 작성/수정 | | ✓ |
| Cloud Run 설정 | | ✓ |
| gcloud 명령 실행 | | ✓ |
| 이슈 기록 | | ✓ |
| 배포 검증 | | ✓ |

#### 대상 서비스

| 서비스 | 플랫폼 | 용도 |
|--------|--------|------|
| `jobbot-backend` | Cloud Run Service | FastAPI 백엔드 |
| `jobbot-frontend` | Cloud Run Service | React 프론트엔드 |
| `jobbot-crawler` | Cloud Run Jobs | 스케줄 크롤링 |

**공통 설정:**
- 리전: `asia-northeast3` (서울)
- 플랫폼: Cloud Run (managed)

#### Codex 배포 요청 형식

Claude가 배포 계획 수립 후 아래 형식으로 출력 → 사용자가 Codex에 복사-붙여넣기:

```
[Codex 배포 요청]

## 1. 배포 대상
- 서비스: backend / frontend / crawler
- 환경: dev / staging / prod

## 2. Claude 계획
- 배포 전략: (신규 배포 / 업데이트 / 롤백)
- 변경 사항: (요약)
- 예상 다운타임: (없음 / 있음)

## 3. 실행 항목
- [ ] Dockerfile 확인/수정
- [ ] Cloud Run 서비스 설정
- [ ] 환경변수 설정
- [ ] 배포 실행
- [ ] 헬스체크 확인

## 4. 환경변수 (시크릿 제외)
- ENVIRONMENT=production
- ...

## 5. 주의사항
- (있다면 기술)

## 6. 롤백 계획
- (이전 리비전으로 롤백 방법)
```

#### Codex 절대 규칙 (deploy/AGENTS.md)

```
⚠️ 배포 전 반드시 이슈 먼저!

배포 요청 수신 → 사전 체크 (보안, 시크릿) → 기존 이슈 조회 → 이슈 생성
             → 배포 계획 기록 → 배포 실행 → 검증 → 이슈 닫기
```

#### 보안 체크리스트 (필수)

- [ ] 시크릿이 코드에 노출되지 않음
- [ ] 환경변수가 Secret Manager 사용
- [ ] .env 파일이 gitignore에 포함
- [ ] 롤백 계획 준비됨

#### 필수 시크릿 목록

| 시크릿 이름 | 용도 | 서비스 |
|------------|------|--------|
| `gemini-api-key` | Gemini API | backend |
| `firestore-key` | Firestore 인증 | backend, crawler |
| `proxy-credentials` | IPRoyal 프록시 | crawler |

#### 이슈 관리 구조

```
deploy/.codex/issues/
├── _TEMPLATE.md              # 배포 이슈 템플릿
└── NNN_deploy_서비스_환경.md # 배포 이슈
```

#### 문서 참조

- **배포 에이전트 규칙**: `deploy/AGENTS.md`
- **배포 이슈 템플릿**: `deploy/.codex/issues/_TEMPLATE.md`

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
