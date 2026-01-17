# JobBot

자연어 기반 채용공고 검색 서비스

## 개요

사용자가 자연어로 채용 조건을 입력하면, AI가 조건을 파싱하여 DB에서 매칭되는 채용공고를 검색하고 결과를 제공합니다.

```
사용자: "강남역 근처 웹디자이너, 연봉 4천 이상 찾아줘"

AI: "강남역 기준 웹디자이너 채용공고 5건을 찾았습니다..."
```

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| Frontend | React + TypeScript + Vite + Tailwind CSS |
| Backend | Python 3.11+ + FastAPI |
| AI | Gemini 2.5 Flash-Lite (Function Calling) |
| Database | Firestore |
| Hosting | Firebase Hosting + Cloud Run |
| Crawler | Python + Cloud Run Jobs |

## 프로젝트 구조

```
jobbot/
├── backend/          # FastAPI 백엔드
├── crawler/          # 잡코리아 크롤러
├── frontend/         # React 프론트엔드
├── docs/             # 문서
├── scripts/          # 설정 스크립트
├── firebase.json     # Firebase 설정
└── firestore.*.json  # Firestore 인덱스/규칙
```

## 시작하기

### 1. 환경 설정

```bash
# GCP 환경 자동 설정
./scripts/setup-gcp.sh [프로젝트ID]

# .env 파일에서 GEMINI_API_KEY 설정
```

### 2. Backend 실행

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend 실행

```bash
cd frontend
npm install
npm run dev
```

### 4. Crawler 실행 (선택)

```bash
cd crawler
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

## API 엔드포인트

- `POST /chat` - 자연어 검색
- `GET /health` - 헬스체크
- `GET /stats` - 서비스 통계

## 배포

```bash
# Backend (Cloud Run)
cd backend && gcloud run deploy jobbot-api --source .

# Frontend (Firebase Hosting)
cd frontend && npm run build && firebase deploy --only hosting

# Crawler (Cloud Run Jobs)
cd crawler && gcloud run jobs create jobbot-crawler --image gcr.io/$PROJECT_ID/jobbot-crawler
```

## 라이센스

MIT
