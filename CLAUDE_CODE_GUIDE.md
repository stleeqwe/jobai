# JobBot 프로젝트 개발 가이드

> 이 문서는 Claude Code에서 직접 참조하여 개발을 진행할 수 있도록 작성된 상세 가이드입니다.

---

## 프로젝트 개요

### 서비스명
JobBot (자연어 기반 채용공고 검색 서비스)

### 핵심 기능
사용자가 자연어로 채용 조건을 입력하면, AI가 조건을 파싱하여 DB에서 매칭되는 채용공고를 검색하고 결과를 제공합니다. 검색 결과에서 공고를 클릭하면 잡코리아 원본 페이지로 이동합니다.

### 사용자 시나리오 예시
```
사용자: "천호동에서 1시간 이내, 웹디자이너, 연봉 4천 이상 찾아줘"

AI 응답: "천호동 기준 1시간 이내 출퇴근 가능한 웹디자이너 채용공고 5건을 찾았습니다.

1. [주식회사 테크스타트] 웹 디자이너 채용
   - 위치: 서울 강남구
   - 연봉: 4,000~5,000만원
   - 경력: 3년 이상
   → 상세보기 (잡코리아 링크)
   
2. ..."
```

---

## 기술 스택

| 레이어 | 기술 | 비고 |
|--------|------|------|
| 프론트엔드 | React + TypeScript + Vite | Tailwind CSS |
| 호스팅 | Firebase Hosting | 정적 빌드 배포 |
| 백엔드 | Python 3.11+ + FastAPI | Cloud Run 배포 |
| AI | Gemini 2.5 Flash-Lite | Function Calling 사용 |
| DB | Firestore | NoSQL, 무료 티어 활용 |
| 크롤러 | Python + Cloud Run Jobs | 매일 새벽 실행 |
| 스케줄러 | Cloud Scheduler | 크롤러 트리거 |

---

## 프로젝트 디렉토리 구조

```
jobbot/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI 엔트리포인트
│   │   ├── config.py                  # 환경변수, 설정 관리
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   └── chat.py                # POST /chat 엔드포인트
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── gemini.py              # Gemini API 클라이언트
│   │   │   ├── job_search.py          # DB 검색 로직
│   │   │   └── location.py            # 위치/통근시간 처리
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── schemas.py             # Pydantic 모델 정의
│   │   └── db/
│   │       ├── __init__.py
│   │       └── firestore.py           # Firestore 클라이언트
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_chat.py
│   │   └── test_search.py
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
│
├── crawler/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # 크롤러 메인 실행
│   │   ├── config.py
│   │   ├── scrapers/
│   │   │   ├── __init__.py
│   │   │   ├── jobkorea.py            # 잡코리아 스크래퍼
│   │   │   └── parser.py              # HTML 파싱 유틸
│   │   ├── normalizers/
│   │   │   ├── __init__.py
│   │   │   ├── job_type.py            # 직무명 정규화
│   │   │   ├── location.py            # 지역명 정규화
│   │   │   └── salary.py              # 급여 파싱
│   │   └── db/
│   │       └── firestore.py           # DB 저장 로직
│   ├── Dockerfile
│   ├── requirements.txt
│   └── README.md
│
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── ChatWindow.tsx         # 메인 채팅 컨테이너
│   │   │   ├── MessageList.tsx        # 메시지 목록
│   │   │   ├── MessageBubble.tsx      # 개별 메시지 버블
│   │   │   ├── JobCard.tsx            # 채용공고 카드 컴포넌트
│   │   │   ├── JobCardList.tsx        # 채용공고 목록
│   │   │   ├── InputBox.tsx           # 입력창
│   │   │   └── LoadingIndicator.tsx   # 로딩 표시
│   │   ├── hooks/
│   │   │   ├── useChat.ts             # 채팅 상태 관리
│   │   │   └── useApi.ts              # API 호출 훅
│   │   ├── services/
│   │   │   └── api.ts                 # API 클라이언트
│   │   ├── types/
│   │   │   └── index.ts               # TypeScript 타입 정의
│   │   └── styles/
│   │       └── index.css              # Tailwind 설정
│   ├── public/
│   │   └── favicon.ico
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── firebase.json
│   └── .firebaserc
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── API.md
│   └── DEPLOYMENT.md
│
├── scripts/
│   ├── setup-gcp.sh                   # GCP 프로젝트 설정
│   └── deploy.sh                      # 배포 스크립트
│
├── .gitignore
└── README.md
```

---

## Firestore 데이터 스키마

### Collection: `jobs`

```javascript
{
  // Document ID: 잡코리아 공고 ID 기반 (예: "jk_12345678")
  
  // === 기본 정보 ===
  "id": "jk_12345678",                        // 공고 고유 ID
  "source": "jobkorea",                       // 데이터 출처
  "company_name": "주식회사 테크스타트",        // 회사명
  "title": "웹 디자이너 신입/경력 채용",        // 공고 제목
  "url": "https://www.jobkorea.co.kr/Recruit/GI_Read/12345678",  // 원본 링크
  
  // === 직무 정보 ===
  "job_type": "웹디자이너",                    // 정규화된 직무명 (검색용)
  "job_type_raw": "UI/UX 웹디자이너",          // 원본 직무명
  "job_category": "디자인",                    // 직무 대분류
  "job_keywords": ["UI", "UX", "웹디자인", "피그마", "포토샵"],  // 키워드
  
  // === 위치 정보 ===
  "location_sido": "서울",                    // 시/도
  "location_gugun": "강남구",                  // 구/군
  "location_dong": "역삼동",                   // 동 (있는 경우)
  "location_full": "서울 강남구 역삼동",        // 전체 주소
  "location_detail": "강남역 3번출구 도보 5분", // 상세 위치 (있는 경우)
  
  // === 자격 조건 ===
  "experience_type": "경력무관",               // 신입 | 경력 | 경력무관
  "experience_min": 0,                        // 최소 경력 (년), null이면 무관
  "experience_max": null,                     // 최대 경력 (년), null이면 무관
  "education": "대졸",                        // 학력 조건
  "education_level": 4,                       // 학력 레벨 (1:무관, 2:고졸, 3:초대졸, 4:대졸, 5:석사, 6:박사)
  
  // === 고용 조건 ===
  "employment_type": "정규직",                // 정규직 | 계약직 | 인턴 | 프리랜서 | 아르바이트
  "employment_type_code": "regular",          // regular | contract | intern | freelance | parttime
  
  // === 급여 정보 ===
  "salary_text": "3,500~4,500만원",           // 원본 급여 텍스트
  "salary_min": 3500,                         // 파싱된 최소 연봉 (만원), null이면 미공개
  "salary_max": 4500,                         // 파싱된 최대 연봉 (만원)
  "salary_type": "annual",                    // annual | monthly | hourly | negotiable | null
  "salary_negotiable": false,                 // 협의 여부
  
  // === 날짜 정보 ===
  "deadline": "2026-01-31",                   // 마감일 (ISO 8601)
  "deadline_type": "date",                    // date | ongoing | asap
  "posted_at": "2026-01-10",                  // 게시일
  
  // === 메타 정보 ===
  "crawled_at": "2026-01-12T03:00:00Z",       // 최초 크롤링 시점 (ISO 8601)
  "updated_at": "2026-01-12T03:00:00Z",       // 마지막 업데이트 시점
  "is_active": true,                          // 활성 상태
  "view_count": 0                             // 조회수 (선택)
}
```

### Collection: `crawl_logs`

```javascript
{
  // Document ID: 날짜 (예: "2026-01-12")
  
  "id": "2026-01-12",
  "started_at": "2026-01-12T03:00:00Z",
  "finished_at": "2026-01-12T03:45:00Z",
  "duration_seconds": 2700,
  
  // 통계
  "total_crawled": 15420,                     // 전체 수집 건수
  "new_jobs": 342,                            // 신규 공고
  "updated_jobs": 1205,                       // 업데이트된 공고
  "expired_jobs": 89,                         // 만료 처리된 공고
  "failed_jobs": 12,                          // 실패한 건수
  
  // 상태
  "status": "success",                        // success | failed | partial
  "error": null,                              // 에러 메시지 (실패 시)
  "error_details": []                         // 상세 에러 로그
}
```

### Firestore 인덱스 설정

```
// firestore.indexes.json
{
  "indexes": [
    {
      "collectionGroup": "jobs",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "is_active", "order": "ASCENDING" },
        { "fieldPath": "job_type", "order": "ASCENDING" },
        { "fieldPath": "location_gugun", "order": "ASCENDING" }
      ]
    },
    {
      "collectionGroup": "jobs",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "is_active", "order": "ASCENDING" },
        { "fieldPath": "location_sido", "order": "ASCENDING" },
        { "fieldPath": "salary_min", "order": "ASCENDING" }
      ]
    },
    {
      "collectionGroup": "jobs",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "is_active", "order": "ASCENDING" },
        { "fieldPath": "job_category", "order": "ASCENDING" },
        { "fieldPath": "experience_type", "order": "ASCENDING" }
      ]
    },
    {
      "collectionGroup": "jobs",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "is_active", "order": "ASCENDING" },
        { "fieldPath": "crawled_at", "order": "DESCENDING" }
      ]
    }
  ]
}
```

---

## API 설계

### Base URL
- 로컬: `http://localhost:8000`
- 프로덕션: `https://jobbot-api-XXXXX.run.app`

### Endpoints

#### POST /chat

사용자 메시지를 받아 AI 응답과 매칭된 채용공고 반환

**Request:**
```json
{
  "message": "천호동에서 1시간 이내, 웹디자이너, 연봉 4천 이상 찾아줘",
  "conversation_id": "optional-uuid-for-context"
}
```

**Response (성공 - V2 아키텍처):**
```json
{
  "success": true,
  "response": "천호동 기준 1시간 이내 출퇴근 가능한 웹디자이너 채용공고 23건을 찾았습니다.",
  "jobs": [
    {
      "id": "jk_12345678",
      "company_name": "주식회사 테크스타트",
      "title": "웹 디자이너 채용",
      "location": "서울 강남구",
      "salary": "4,000~5,000만원",
      "experience": "경력 3년 이상",
      "employment_type": "정규직",
      "deadline": "2026-01-31",
      "url": "https://www.jobkorea.co.kr/Recruit/GI_Read/12345678"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_count": 23,
    "total_pages": 2,
    "has_next": true,
    "has_prev": false
  },
  "filter_params": {
    "locations": ["강남구", "송파구", "강동구"],
    "salary_min": 4000
  },
  "job_query": "웹디자이너",
  "conversation_id": "uuid-xxxxx"
}
```

**Response (검색 결과 없음):**
```json
{
  "success": true,
  "response": "죄송합니다. 조건에 맞는 채용공고를 찾지 못했습니다. 조건을 조금 완화해보시겠어요?",
  "jobs": [],
  "total_count": 0,
  "search_params": {...},
  "conversation_id": "uuid-xxxxx"
}
```

**Response (에러):**
```json
{
  "success": false,
  "error": "서비스 일시 오류",
  "error_code": "INTERNAL_ERROR",
  "conversation_id": "uuid-xxxxx"
}
```

#### GET /health

헬스체크 엔드포인트

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-12T10:00:00Z",
  "version": "1.0.0",
  "services": {
    "firestore": "connected",
    "gemini": "available"
  }
}
```

#### GET /stats (선택적)

서비스 통계 조회

**Response:**
```json
{
  "total_jobs": 15420,
  "active_jobs": 14200,
  "last_crawl": "2026-01-12T03:45:00Z",
  "job_categories": {
    "IT개발": 5420,
    "디자인": 2100,
    "마케팅": 1800
  }
}
```

---

## 검색 아키텍처 V2 (2-Stage Hybrid)

> **핵심 원칙**: DB는 숫자/범주 필터링, AI는 자연어 이해 담당

### 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────────┐
│                      사용자 입력                                  │
│  "강남역 근처 iOS 프론트 앱 개발자 연봉 5천만원 이상 공고 찾아줘"      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 1: DB 필터링 (명확한 조건만)                               │
│  - 위치: ["강남구", "서초구"]                                     │
│  - 연봉: salary_min >= 5000                                     │
│  - 직무(job_type): 필터 안 함 (AI에게 위임)                       │
│  결과: 10,000건 → ~300건                                        │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 2: AI 선별 (직무 매칭)                                    │
│  - 후보 공고 목록 (id, title)을 AI에게 전달                       │
│  - AI가 "iOS 프론트 앱 개발자"에 해당하는 공고 선별                │
│  결과: 300건 → 관련 있는 모든 공고 ID                             │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 3: 결과 반환                                              │
│  - 선별된 모든 공고 반환 (페이지네이션)                            │
│  - 페이지당 20건                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Stage 1: Function Definition (DB 필터용)

```json
{
  "name": "filter_jobs",
  "description": "명확한 조건으로 DB에서 후보 공고를 필터링합니다. 직무(job_type)는 이 함수에서 필터하지 않습니다.",
  "parameters": {
    "type": "object",
    "properties": {
      "preferred_locations": {
        "type": "array",
        "items": {"type": "string"},
        "description": "선호 지역 리스트 (구/군 단위, 예: ['강남구', '서초구'])"
      },
      "user_location": {
        "type": "string",
        "description": "사용자 출발 위치 (동 단위, 예: '천호동')"
      },
      "commute_time_minutes": {
        "type": "integer",
        "description": "최대 통근시간 (분 단위)"
      },
      "salary_min": {
        "type": "integer",
        "description": "최소 연봉 (만원 단위, 예: 5000 = 5천만원)"
      },
      "experience_type": {
        "type": "string",
        "enum": ["신입", "경력", "경력무관"],
        "description": "경력 조건"
      },
      "employment_type": {
        "type": "string",
        "enum": ["정규직", "계약직", "인턴", "프리랜서"],
        "description": "고용형태"
      }
    },
    "required": []
  }
}
```

### Stage 2: AI 선별 프롬프트

```
다음 후보 공고 목록에서 사용자 요청에 관련 있는 공고를 선별하세요.

사용자 요청: "{job_query}" (예: "iOS 프론트 앱 개발자")

후보 공고:
1. [jk_123] iOS 개발자 채용
2. [jk_456] 백엔드 개발자
3. [jk_789] 모바일 앱 프론트엔드 개발자
...

관련 있는 공고의 ID만 배열로 반환하세요.
응답 형식: ["jk_123", "jk_789", ...]
```

### 2-Stage 처리 플로우

```
1. 사용자 입력 수신
   │
   ▼
2. Gemini: filter_jobs 파라미터 추출 + 직무 쿼리 추출
   │  - filter_params: {locations, salary_min, ...}
   │  - job_query: "iOS 프론트 앱 개발자"
   │
   ▼
3. Stage 1: DB 필터링
   │  - Firestore 쿼리 실행
   │  - 후보 공고 목록 획득 (~300건)
   │
   ▼
4. Stage 2: AI 선별
   │  - 후보 목록을 Gemini에게 전달
   │  - 관련 공고 ID 배열 수신
   │
   ▼
5. 결과 조합 및 페이지네이션
   │
   ▼
6. 최종 응답 생성 (친근한 소개)
```

### 기존 대비 변경점

| 항목 | 기존 | V2 |
|------|------|-----|
| 직무 필터링 | Function Calling (job_type) | AI 직접 판단 |
| 키워드 반영 | 무시됨 | AI가 이해 |
| mvp_category_map | 필요 (복잡한 매핑) | 불필요 |
| 결과 수 | 10개 제한 | 전체 (페이지네이션) |
| "기타" 문제 | 22%+ | 해결 |

---

## 핵심 코드 구현

### backend/app/main.py

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import chat
from app.config import settings

app = FastAPI(
    title="JobBot API",
    description="자연어 기반 채용공고 검색 서비스",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(chat.router, prefix="/chat", tags=["chat"])

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0"
    }
```

### backend/app/config.py

```python
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # GCP
    GOOGLE_CLOUD_PROJECT: str
    GEMINI_API_KEY: str
    
    # App
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]
    
    # Gemini
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"
    
    class Config:
        env_file = ".env"

settings = Settings()
```

### backend/app/services/gemini.py

```python
import google.generativeai as genai
from app.config import settings
from app.services.job_search import search_jobs_in_db
from typing import Dict, Any, List

# API 키 설정
genai.configure(api_key=settings.GEMINI_API_KEY)

# Function 정의
SEARCH_JOBS_FUNCTION = genai.protos.FunctionDeclaration(
    name="search_jobs",
    description="채용공고 데이터베이스에서 조건에 맞는 공고를 검색합니다",
    parameters=genai.protos.Schema(
        type=genai.protos.Type.OBJECT,
        properties={
            "job_type": genai.protos.Schema(type=genai.protos.Type.STRING),
            "job_keywords": genai.protos.Schema(
                type=genai.protos.Type.ARRAY,
                items=genai.protos.Schema(type=genai.protos.Type.STRING)
            ),
            "preferred_locations": genai.protos.Schema(
                type=genai.protos.Type.ARRAY,
                items=genai.protos.Schema(type=genai.protos.Type.STRING)
            ),
            "user_location": genai.protos.Schema(type=genai.protos.Type.STRING),
            "commute_time_minutes": genai.protos.Schema(type=genai.protos.Type.INTEGER),
            "experience_type": genai.protos.Schema(type=genai.protos.Type.STRING),
            "experience_years_min": genai.protos.Schema(type=genai.protos.Type.INTEGER),
            "salary_min": genai.protos.Schema(type=genai.protos.Type.INTEGER),
            "employment_type": genai.protos.Schema(type=genai.protos.Type.STRING),
            "limit": genai.protos.Schema(type=genai.protos.Type.INTEGER),
        }
    )
)

SYSTEM_PROMPT = """
너는 채용공고 검색을 도와주는 AI 어시스턴트 "잡챗"이야.
사용자가 원하는 채용 조건을 파악해서 search_jobs 함수를 호출해.

## 조건 추출 규칙
- 위치: 사용자가 언급한 지역 + 인근 지역을 preferred_locations에 포함
- 통근시간: user_location과 commute_time_minutes로 저장
- 연봉: 만원 단위로 변환 (4천만원 = 4000)
- 조건이 불명확하면 null로 두고 검색

## 응답 규칙
- 검색 결과를 친근하게 소개
- 결과 없으면 조건 완화 제안
- 존댓말 사용
"""

class GeminiService:
    def __init__(self):
        self.model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            tools=[genai.protos.Tool(function_declarations=[SEARCH_JOBS_FUNCTION])],
            system_instruction=SYSTEM_PROMPT
        )
    
    async def process_message(self, message: str) -> Dict[str, Any]:
        chat = self.model.start_chat()
        
        # 첫 번째 응답 받기
        response = chat.send_message(message)
        
        jobs = []
        search_params = {}
        
        # Function Call 처리
        for part in response.parts:
            if fn := part.function_call:
                # 검색 파라미터 추출
                search_params = dict(fn.args)
                
                # DB 검색 실행
                jobs = await search_jobs_in_db(search_params)
                
                # 검색 결과를 모델에 다시 전달
                response = chat.send_message(
                    genai.protos.Content(
                        parts=[genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name="search_jobs",
                                response={
                                    "jobs": jobs,
                                    "total_count": len(jobs)
                                }
                            )
                        )]
                    )
                )
        
        # 최종 텍스트 응답 추출
        response_text = ""
        for part in response.parts:
            if part.text:
                response_text += part.text
        
        return {
            "response": response_text,
            "jobs": jobs,
            "search_params": search_params
        }

gemini_service = GeminiService()
```

### backend/app/services/job_search.py (V2 아키텍처)

```python
from google.cloud import firestore
from typing import Dict, Any, List
from app.services.location import estimate_reachable_locations

db = firestore.AsyncClient()

async def filter_jobs_by_conditions(params: Dict[str, Any]) -> List[Dict]:
    """
    Stage 1: DB에서 명확한 조건으로 후보 공고 필터링

    NOTE: job_type, job_category는 필터하지 않음 (AI에게 위임)
    """
    query = db.collection("jobs").where("is_active", "==", True)

    # 위치 필터
    locations = params.get("preferred_locations", [])

    # 통근시간 기반 위치 추정
    if user_location := params.get("user_location"):
        commute_time = params.get("commute_time_minutes", 60)
        estimated_locations = estimate_reachable_locations(user_location, commute_time)
        locations = list(set(locations + estimated_locations))

    if locations:
        # Firestore는 in 쿼리가 최대 30개까지만 지원
        locations = locations[:30]
        query = query.where("location_gugun", "in", locations)

    # 경력 필터
    if experience_type := params.get("experience_type"):
        if experience_type == "신입":
            query = query.where("experience_type", "in", ["신입", "경력무관"])
        elif experience_type == "경력":
            query = query.where("experience_type", "in", ["경력", "경력무관"])

    # 고용형태 필터
    if employment_type := params.get("employment_type"):
        query = query.where("employment_type", "==", employment_type)

    # NOTE: limit 없이 전체 후보 가져옴 (AI 선별용)
    # 쿼리 실행
    docs = query.stream()

    candidates = []
    async for doc in docs:
        job = doc.to_dict()

        # 연봉 필터 (클라이언트 사이드)
        if salary_min := params.get("salary_min"):
            if job.get("salary_min") is None or job.get("salary_min") < salary_min:
                continue

        # AI 선별용 최소 정보만 포함
        candidates.append({
            "id": job["id"],
            "title": job["title"],
            "company_name": job["company_name"],
            "job_type_raw": job.get("job_type_raw", ""),
            # 전체 데이터도 보관 (나중에 결과 조합 시 사용)
            "_full_data": job
        })

    return candidates


async def get_jobs_by_ids(
    candidates: List[Dict],
    selected_ids: List[str],
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    """
    Stage 3: AI가 선별한 ID 목록을 기반으로 결과 조합

    Args:
        candidates: Stage 1에서 가져온 후보 목록 (_full_data 포함)
        selected_ids: Stage 2에서 AI가 선별한 ID 목록
        page: 페이지 번호 (1부터 시작)
        page_size: 페이지당 결과 수
    """
    # 선별된 ID로 필터링
    id_set = set(selected_ids)
    selected_jobs = [c for c in candidates if c["id"] in id_set]

    # 페이지네이션 계산
    total_count = len(selected_jobs)
    total_pages = (total_count + page_size - 1) // page_size

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_jobs = selected_jobs[start_idx:end_idx]

    # 응답 포맷팅
    results = []
    for job in page_jobs:
        full = job["_full_data"]
        results.append({
            "id": full["id"],
            "company_name": full["company_name"],
            "title": full["title"],
            "location": full.get("location_full", ""),
            "salary": full.get("salary_text", "협의"),
            "experience": f"{full.get('experience_type', '')}" + (
                f" {full.get('experience_min', 0)}년 이상"
                if full.get("experience_min") else ""
            ),
            "employment_type": full.get("employment_type", ""),
            "deadline": full.get("deadline", ""),
            "url": full["url"]
        })

    return {
        "jobs": results,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }
    }
```

### backend/app/services/location.py

```python
from typing import List

# 서울 지역 인접 정보 (간략화)
SEOUL_ADJACENCY = {
    "강남구": ["서초구", "송파구", "강동구", "성동구"],
    "서초구": ["강남구", "동작구", "관악구", "방배동"],
    "송파구": ["강남구", "강동구", "광진구"],
    "강동구": ["송파구", "강남구", "광진구", "하남시"],
    "마포구": ["서대문구", "용산구", "영등포구", "은평구"],
    "영등포구": ["마포구", "동작구", "구로구", "양천구"],
    # ... 더 추가 가능
}

# 동별 구 매핑 (주요 동만)
DONG_TO_GU = {
    "천호동": "강동구",
    "역삼동": "강남구",
    "삼성동": "강남구",
    "잠실동": "송파구",
    "합정동": "마포구",
    "홍대입구": "마포구",
    "강남역": "강남구",
    "신촌": "서대문구",
    # ... 더 추가 가능
}

def estimate_reachable_locations(user_location: str, commute_minutes: int) -> List[str]:
    """
    사용자 위치와 통근시간을 기반으로 도달 가능한 구 목록 추정
    
    NOTE: 이 함수는 단순 추정입니다. 정확한 경로탐색 API 대신
    LLM의 상식을 활용하거나, 사전 정의된 인접 정보를 사용합니다.
    """
    # 동 → 구 변환
    base_gu = DONG_TO_GU.get(user_location)
    if not base_gu:
        # 이미 구 단위인 경우
        base_gu = user_location if user_location.endswith("구") else None
    
    if not base_gu:
        # 알 수 없는 위치면 서울 전체 반환
        return list(SEOUL_ADJACENCY.keys())
    
    reachable = {base_gu}
    
    # 30분 이내: 인접 구
    if commute_minutes >= 30:
        adjacent = SEOUL_ADJACENCY.get(base_gu, [])
        reachable.update(adjacent)
    
    # 60분 이내: 인접의 인접
    if commute_minutes >= 60:
        for gu in list(reachable):
            second_adjacent = SEOUL_ADJACENCY.get(gu, [])
            reachable.update(second_adjacent)
    
    # 90분 이상: 서울 전체
    if commute_minutes >= 90:
        reachable.update(SEOUL_ADJACENCY.keys())
    
    return list(reachable)
```

### backend/app/routers/chat.py

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import uuid

from app.services.gemini import gemini_service

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None

class JobItem(BaseModel):
    id: str
    company_name: str
    title: str
    location: str
    salary: str
    experience: str
    employment_type: str
    deadline: str
    url: str

class ChatResponse(BaseModel):
    success: bool
    response: str
    jobs: List[JobItem]
    total_count: int
    search_params: dict
    conversation_id: str
    error: Optional[str] = None

@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        # 대화 ID 생성 또는 사용
        conversation_id = request.conversation_id or str(uuid.uuid4())
        
        # Gemini 처리
        result = await gemini_service.process_message(request.message)
        
        return ChatResponse(
            success=True,
            response=result["response"],
            jobs=result["jobs"],
            total_count=len(result["jobs"]),
            search_params=result["search_params"],
            conversation_id=conversation_id
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### backend/requirements.txt

```
fastapi==0.109.0
uvicorn[standard]==0.27.0
google-cloud-firestore==2.14.0
google-generativeai==0.3.2
pydantic==2.5.3
pydantic-settings==2.1.0
python-dotenv==1.0.0
httpx==0.26.0
```

### backend/Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 복사
COPY app/ ./app/

# 포트 설정
EXPOSE 8080

# 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

## 크롤러 구현

### crawler/app/main.py

```python
import asyncio
from datetime import datetime
from app.scrapers.jobkorea import JobKoreaScraper
from app.db.firestore import save_jobs, save_crawl_log
from app.config import settings

async def main():
    print(f"[{datetime.now()}] 크롤링 시작")
    
    scraper = JobKoreaScraper()
    crawl_log = {
        "started_at": datetime.now().isoformat(),
        "total_crawled": 0,
        "new_jobs": 0,
        "updated_jobs": 0,
        "failed_jobs": 0,
        "status": "running"
    }
    
    try:
        # 잡코리아 크롤링
        jobs = await scraper.crawl_all()
        crawl_log["total_crawled"] = len(jobs)
        
        # DB 저장
        result = await save_jobs(jobs)
        crawl_log["new_jobs"] = result["new"]
        crawl_log["updated_jobs"] = result["updated"]
        
        crawl_log["status"] = "success"
        
    except Exception as e:
        crawl_log["status"] = "failed"
        crawl_log["error"] = str(e)
        print(f"크롤링 실패: {e}")
    
    finally:
        crawl_log["finished_at"] = datetime.now().isoformat()
        await save_crawl_log(crawl_log)
        print(f"[{datetime.now()}] 크롤링 완료: {crawl_log}")

if __name__ == "__main__":
    asyncio.run(main())
```

### crawler/app/scrapers/jobkorea.py

```python
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict
import asyncio
from app.normalizers.job_type import normalize_job_type
from app.normalizers.location import normalize_location
from app.normalizers.salary import parse_salary

class JobKoreaScraper:
    BASE_URL = "https://www.jobkorea.co.kr"
    LIST_URL = f"{BASE_URL}/recruit/joblist"
    
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
        )
    
    async def crawl_all(self) -> List[Dict]:
        """전체 채용공고 크롤링"""
        all_jobs = []
        page = 1
        
        while True:
            jobs = await self.crawl_page(page)
            if not jobs:
                break
            
            all_jobs.extend(jobs)
            page += 1
            
            # 부하 방지
            await asyncio.sleep(1)
            
            # 개발 중에는 제한
            if page > 10:  # TODO: 프로덕션에서 제거
                break
        
        return all_jobs
    
    async def crawl_page(self, page: int) -> List[Dict]:
        """목록 페이지 크롤링"""
        params = {
            "page": page,
            "stext": "",  # 전체 검색
        }
        
        response = await self.client.get(self.LIST_URL, params=params)
        soup = BeautifulSoup(response.text, "html.parser")
        
        jobs = []
        for item in soup.select(".list-item"):
            try:
                job = self.parse_list_item(item)
                if job:
                    jobs.append(job)
            except Exception as e:
                print(f"파싱 실패: {e}")
                continue
        
        return jobs
    
    def parse_list_item(self, item) -> Dict:
        """목록 아이템 파싱"""
        # 공고 ID 추출
        link = item.select_one("a.title")
        if not link:
            return None
        
        href = link.get("href", "")
        job_id = href.split("/")[-1] if "/" in href else None
        if not job_id:
            return None
        
        # 기본 정보
        company = item.select_one(".company-name")
        title = item.select_one(".title")
        
        # 조건 정보
        conditions = item.select(".conditions span")
        experience_raw = conditions[0].text.strip() if len(conditions) > 0 else ""
        education_raw = conditions[1].text.strip() if len(conditions) > 1 else ""
        location_raw = conditions[2].text.strip() if len(conditions) > 2 else ""
        job_type_raw = conditions[3].text.strip() if len(conditions) > 3 else ""
        
        # 마감일
        deadline_el = item.select_one(".date")
        deadline = deadline_el.text.strip() if deadline_el else ""
        
        # 정규화
        location_info = normalize_location(location_raw)
        salary_info = parse_salary(item.select_one(".salary"))
        
        return {
            "id": f"jk_{job_id}",
            "source": "jobkorea",
            "company_name": company.text.strip() if company else "",
            "title": title.text.strip() if title else "",
            "url": f"{self.BASE_URL}{href}",
            
            "job_type": normalize_job_type(job_type_raw),
            "job_type_raw": job_type_raw,
            
            "location_sido": location_info["sido"],
            "location_gugun": location_info["gugun"],
            "location_full": location_raw,
            
            "experience_type": self.parse_experience_type(experience_raw),
            "education": education_raw,
            
            "salary_text": salary_info["text"],
            "salary_min": salary_info["min"],
            "salary_max": salary_info["max"],
            "salary_type": salary_info["type"],
            
            "deadline": self.parse_deadline(deadline),
            "employment_type": "정규직",  # 기본값, 상세 페이지에서 갱신 필요
            
            "is_active": True
        }
    
    def parse_experience_type(self, text: str) -> str:
        if "신입" in text and "경력" in text:
            return "경력무관"
        elif "신입" in text:
            return "신입"
        elif "경력" in text:
            return "경력"
        return "경력무관"
    
    def parse_deadline(self, text: str) -> str:
        # TODO: 날짜 파싱 로직
        return text
```

### crawler/requirements.txt

```
httpx==0.26.0
beautifulsoup4==4.12.3
google-cloud-firestore==2.14.0
python-dotenv==1.0.0
lxml==5.1.0
```

---

## 프론트엔드 구현

### frontend/src/App.tsx

```tsx
import { ChatWindow } from './components/ChatWindow'

function App() {
  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-white shadow-sm">
        <div className="max-w-4xl mx-auto py-4 px-4">
          <h1 className="text-2xl font-bold text-gray-900">
            잡챗 💼
          </h1>
          <p className="text-sm text-gray-500">
            자연어로 채용공고를 검색해보세요
          </p>
        </div>
      </header>
      
      <main className="max-w-4xl mx-auto py-6 px-4">
        <ChatWindow />
      </main>
    </div>
  )
}

export default App
```

### frontend/src/components/ChatWindow.tsx

```tsx
import { useState } from 'react'
import { MessageList } from './MessageList'
import { InputBox } from './InputBox'
import { useChat } from '../hooks/useChat'

export function ChatWindow() {
  const { messages, isLoading, sendMessage } = useChat()
  
  return (
    <div className="bg-white rounded-lg shadow-lg overflow-hidden">
      <div className="h-[600px] flex flex-col">
        {/* 메시지 영역 */}
        <div className="flex-1 overflow-y-auto p-4">
          <MessageList messages={messages} isLoading={isLoading} />
        </div>
        
        {/* 입력 영역 */}
        <div className="border-t p-4">
          <InputBox onSend={sendMessage} disabled={isLoading} />
        </div>
      </div>
    </div>
  )
}
```

### frontend/src/components/MessageBubble.tsx

```tsx
import { Message } from '../types'
import { JobCardList } from './JobCardList'

interface Props {
  message: Message
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'
  
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2 ${
          isUser
            ? 'bg-blue-500 text-white'
            : 'bg-gray-100 text-gray-900'
        }`}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        
        {/* 채용공고 목록 */}
        {message.jobs && message.jobs.length > 0 && (
          <div className="mt-3">
            <JobCardList jobs={message.jobs} />
          </div>
        )}
      </div>
    </div>
  )
}
```

### frontend/src/components/JobCard.tsx

```tsx
import { Job } from '../types'

interface Props {
  job: Job
}

export function JobCard({ job }: Props) {
  return (
    <a
      href={job.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block bg-white border rounded-lg p-3 hover:shadow-md transition-shadow"
    >
      <div className="font-medium text-gray-900 mb-1">
        {job.title}
      </div>
      <div className="text-sm text-gray-600 mb-2">
        {job.company_name}
      </div>
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="bg-gray-100 px-2 py-1 rounded">
          📍 {job.location}
        </span>
        <span className="bg-gray-100 px-2 py-1 rounded">
          💰 {job.salary}
        </span>
        <span className="bg-gray-100 px-2 py-1 rounded">
          👤 {job.experience}
        </span>
      </div>
      <div className="mt-2 text-xs text-gray-500">
        마감: {job.deadline}
      </div>
    </a>
  )
}
```

### frontend/src/hooks/useChat.ts

```tsx
import { useState, useCallback } from 'react'
import { Message, Job } from '../types'
import { chatApi } from '../services/api'

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: '안녕하세요! 원하시는 채용 조건을 자연어로 말씀해주세요. 예: "강남역 근처 웹디자이너, 연봉 4천 이상"',
      jobs: []
    }
  ])
  const [isLoading, setIsLoading] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  
  const sendMessage = useCallback(async (content: string) => {
    // 사용자 메시지 추가
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content,
      jobs: []
    }
    setMessages(prev => [...prev, userMessage])
    setIsLoading(true)
    
    try {
      const response = await chatApi.send(content, conversationId)
      
      // AI 응답 추가
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.response,
        jobs: response.jobs
      }
      setMessages(prev => [...prev, assistantMessage])
      setConversationId(response.conversation_id)
      
    } catch (error) {
      // 에러 처리
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: '죄송합니다. 오류가 발생했습니다. 다시 시도해주세요.',
        jobs: []
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }, [conversationId])
  
  return { messages, isLoading, sendMessage }
}
```

### frontend/src/services/api.ts

```tsx
import axios from 'axios'
import { ChatResponse } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json'
  }
})

export const chatApi = {
  send: async (message: string, conversationId: string | null): Promise<ChatResponse> => {
    const response = await client.post('/chat', {
      message,
      conversation_id: conversationId
    })
    return response.data
  }
}
```

### frontend/src/types/index.ts

```tsx
export interface Job {
  id: string
  company_name: string
  title: string
  location: string
  salary: string
  experience: string
  employment_type: string
  deadline: string
  url: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  jobs: Job[]
}

export interface ChatResponse {
  success: boolean
  response: string
  jobs: Job[]
  total_count: number
  search_params: Record<string, any>
  conversation_id: string
  error?: string
}
```

### frontend/package.json

```json
{
  "name": "jobbot-frontend",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "deploy": "npm run build && firebase deploy --only hosting"
  },
  "dependencies": {
    "axios": "^1.6.5",
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.48",
    "@types/react-dom": "^18.2.18",
    "@vitejs/plugin-react": "^4.2.1",
    "autoprefixer": "^10.4.17",
    "postcss": "^8.4.33",
    "tailwindcss": "^3.4.1",
    "typescript": "^5.3.3",
    "vite": "^5.0.12"
  }
}
```

---

## 개발 환경 설정

### 사전 요구사항 (Mac M4)

```bash
# Homebrew로 설치
brew install python@3.11
brew install node@20
brew install --cask google-cloud-sdk

# Firebase CLI
npm install -g firebase-tools
```

### GCP 프로젝트 설정

```bash
# 1. GCP 프로젝트 생성
gcloud projects create jobbot-project --name="JobBot"
gcloud config set project jobbot-project

# 2. 필요한 API 활성화
gcloud services enable firestore.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable generativelanguage.googleapis.com

# 3. Firestore 데이터베이스 생성 (서울 리전)
gcloud firestore databases create --location=asia-northeast3

# 4. 서비스 계정 생성 (로컬 개발용)
gcloud iam service-accounts create jobbot-dev \
  --display-name="JobBot Dev"

gcloud projects add-iam-policy-binding jobbot-project \
  --member="serviceAccount:jobbot-dev@jobbot-project.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

# 5. 키 파일 다운로드
gcloud iam service-accounts keys create ~/jobbot-key.json \
  --iam-account=jobbot-dev@jobbot-project.iam.gserviceaccount.com

# 6. 환경변수 설정
export GOOGLE_APPLICATION_CREDENTIALS=~/jobbot-key.json
```

### Gemini API 키 발급

1. Google AI Studio 접속: https://makersuite.google.com/app/apikey
2. "Create API Key" 클릭
3. 키 복사 후 `.env` 파일에 저장

### 로컬 개발 실행

```bash
# Backend
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# .env 파일 생성
cat > .env << EOF
GOOGLE_CLOUD_PROJECT=jobbot-project
GEMINI_API_KEY=your-api-key-here
ENVIRONMENT=development
EOF

# 실행
uvicorn app.main:app --reload --port 8000

# Frontend (새 터미널)
cd frontend
npm install
npm run dev
```

---

## 배포

### Backend (Cloud Run)

```bash
cd backend

# 빌드 및 배포
gcloud run deploy jobbot-api \
  --source . \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=jobbot-project,GEMINI_API_KEY=your-key"
```

### Frontend (Firebase Hosting)

```bash
cd frontend

# Firebase 초기화
firebase init hosting

# 빌드 및 배포
npm run build
firebase deploy --only hosting
```

### Crawler (Cloud Run Jobs)

```bash
cd crawler

# 이미지 빌드
gcloud builds submit --tag gcr.io/jobbot-project/jobbot-crawler

# Job 생성
gcloud run jobs create jobbot-crawler \
  --image gcr.io/jobbot-project/jobbot-crawler \
  --region asia-northeast3

# 스케줄러 설정 (매일 새벽 3시)
gcloud scheduler jobs create http crawl-daily \
  --location asia-northeast3 \
  --schedule "0 3 * * *" \
  --uri "https://asia-northeast3-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/jobbot-project/jobs/jobbot-crawler:run" \
  --http-method POST \
  --oauth-service-account-email jobbot-dev@jobbot-project.iam.gserviceaccount.com
```

---

## 개발 순서 (권장)

### Phase 1: 환경 설정 (1일)
1. GCP 프로젝트 생성
2. Firestore 데이터베이스 생성
3. Gemini API 키 발급
4. 로컬 개발환경 설정

### Phase 2: 크롤러 (2-3일)
1. 잡코리아 목록 페이지 크롤링
2. 데이터 파싱 및 정규화
3. Firestore 저장
4. 테스트 (100개 샘플)

### Phase 3: Backend API (2-3일)
1. FastAPI 기본 구조
2. Gemini Function Calling 연동
3. DB 검색 로직
4. API 테스트

### Phase 4: Frontend (2일)
1. React 프로젝트 설정
2. 채팅 UI 구현
3. API 연동

### Phase 5: 배포 (1일)
1. Cloud Run 배포 (Backend)
2. Firebase Hosting 배포 (Frontend)
3. Cloud Scheduler 설정 (Crawler)

### Phase 6: 테스트 및 개선 (ongoing)
1. 실사용 테스트
2. 프롬프트 튜닝
3. 버그 수정

---

## 참고 사항

### 비용 추정 (MVP, 일 500명 기준)

| 서비스 | 무료 티어 | 예상 비용 |
|--------|----------|----------|
| Firebase Hosting | 10GB/월 | $0 |
| Cloud Run | 200만 요청/월 | $0 |
| Firestore | 50K 읽기/일 | $0 |
| Gemini Flash-Lite | - | ~$3/월 |
| Cloud Run Jobs | - | ~$1/월 |
| **합계** | | **~$5/월** |

### 법적 고려사항

- 잡코리아 원본 링크 제공으로 트래픽 유입
- 메타정보만 수집, 전문 복제 안 함
- 서버 부하 최소화 (크롤링 속도 조절)
- 문제 제기 시 즉시 대응 준비

### 확장 계획 (향후)

1. 사람인 등 추가 소스 연동
2. 맞춤 추천 기능
3. 알림 기능
4. 이력서 관리

---

*이 문서는 Claude Code에서 직접 참조하여 개발을 진행할 수 있도록 작성되었습니다.*
