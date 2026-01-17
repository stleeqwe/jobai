---
paths:
  - "backend/**/*.py"
---

# Backend Rules

`backend/` 디렉토리의 Python 코드 작업 시 적용되는 규칙입니다.

## 필수 규칙

### 1. Gemini SDK Import
```python
# CORRECT
from google import genai
from google.genai import types

# WRONG - deprecated, 사용 금지
from google.generativeai import ...
```

### 2. 타입 힌트
```python
# CORRECT
async def search_jobs(query: str, limit: int = 50) -> list[dict]:
    ...

# WRONG
def search_jobs(query, limit=50):
    ...
```

### 3. Pydantic 모델 사용
```python
# 요청/응답은 Pydantic 모델로 정의
class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
```

### 4. async/await 패턴
```python
# FastAPI 엔드포인트는 async로
@router.post("/chat")
async def chat(request: ChatRequest):
    ...

# httpx 사용 시 AsyncClient
async with httpx.AsyncClient() as client:
    response = await client.get(url)
```

## 환경변수

### 우선순위
```
.env 파일 > config.py 기본값
```

### 주요 변수
- `GEMINI_API_KEY` - Gemini API 키
- `GEMINI_MODEL` - 사용 모델 (기본: gemini-3-flash-preview)
- `ALLOWED_ORIGINS` - CORS 허용 목록
- `GOOGLE_APPLICATION_CREDENTIALS` - Firestore 인증

## API 엔드포인트

| Method | Path | 용도 |
|--------|------|------|
| POST | `/chat` | 채팅 메시지 처리 |
| POST | `/chat/more` | 추가 결과 조회 |
| GET | `/health` | 헬스체크 |
| GET | `/model-info` | 모델 정보 |

## 테스트

```bash
cd backend && source venv/bin/activate
python -m pytest
python -m pytest tests/test_specific.py::test_function -v
```

## 금지 사항

- `.env` 파일 내용 코드에 하드코딩 금지
- `google.generativeai` 패키지 사용 금지
- Firestore 스키마 임의 변경 금지 (크롤러와 동기화 필요)
- 동기 blocking 코드 사용 금지 (async 사용)
