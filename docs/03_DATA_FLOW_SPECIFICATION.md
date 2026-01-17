# JobBot Data Flow Specification

**Version:** 3.0
**Last Updated:** 2026-01-13

---

## 1. 개요

이 문서는 JobBot 시스템의 데이터 흐름을 상세히 기술합니다.

---

## 2. 사용자 검색 플로우

### 2.1 전체 시퀀스 다이어그램

```
┌──────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│Client│     │ Frontend │     │ Backend  │     │ Gemini   │     │Firestore │     │Maps API  │
└──┬───┘     └────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘
   │              │                │                │                │                │
   │ 1. 메시지 입력│                │                │                │                │
   │─────────────>│                │                │                │                │
   │              │                │                │                │                │
   │              │ 2. GPS 좌표    │                │                │                │
   │              │    (선택적)    │                │                │                │
   │              │                │                │                │                │
   │              │ 3. POST /chat  │                │                │                │
   │              │───────────────>│                │                │                │
   │              │                │                │                │                │
   │              │                │ 4. send_message│                │                │
   │              │                │───────────────>│                │                │
   │              │                │                │                │                │
   │              │                │ 5. Function Call (search_jobs)  │                │
   │              │                │<───────────────│                │                │
   │              │                │                │                │                │
   │              │                │ 6. get_all_active_jobs          │                │
   │              │                │────────────────────────────────>│                │
   │              │                │                │                │                │
   │              │                │ 7. jobs (~1000건)               │                │
   │              │                │<────────────────────────────────│                │
   │              │                │                │                │                │
   │              │                │ 8. Stage 1: 직무 필터           │                │
   │              │                │───────────────>│                │                │
   │              │                │                │                │                │
   │              │                │ 9. filtered_ids (~100건)        │                │
   │              │                │<───────────────│                │                │
   │              │                │                │                │                │
   │              │                │ 10. Stage 2: 연봉 필터 (로컬)   │                │
   │              │                │────────┐      │                │                │
   │              │                │        │      │                │                │
   │              │                │<───────┘ (~80건)               │                │
   │              │                │                │                │                │
   │              │                │ 11. Stage 3: 거리 필터         │                │
   │              │                │───────────────────────────────────────────────>│
   │              │                │                │                │                │
   │              │                │ 12. travel_times               │                │
   │              │                │<──────────────────────────────────────────────│
   │              │                │                │                │                │
   │              │                │ 13. Function Response          │                │
   │              │                │───────────────>│                │                │
   │              │                │                │                │                │
   │              │                │ 14. AI 응답 텍스트              │                │
   │              │                │<───────────────│                │                │
   │              │                │                │                │                │
   │              │ 15. ChatResponse                │                │                │
   │              │<───────────────│                │                │                │
   │              │                │                │                │                │
   │ 16. UI 업데이트               │                │                │                │
   │<─────────────│                │                │                │                │
   │              │                │                │                │                │
```

### 2.2 단계별 데이터 변환

#### Step 1-2: 클라이언트 입력

**사용자 입력:**
```
"강남역 30분 거리 웹디자이너, 연봉 4천 이상"
```

**GPS 좌표 (선택적):**
```json
{
  "latitude": 37.497942,
  "longitude": 127.027621
}
```

#### Step 3: API Request

**POST /chat Request Body:**
```json
{
  "message": "강남역 30분 거리 웹디자이너, 연봉 4천 이상",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "page": 1,
  "page_size": 20,
  "user_lat": 37.497942,
  "user_lng": 127.027621
}
```

#### Step 4-5: Gemini Function Call

**Gemini 입력:**
```
[System Prompt] + "강남역 30분 거리 웹디자이너, 연봉 4천 이상"
```

**Gemini 출력 (Function Call):**
```json
{
  "function_call": {
    "name": "search_jobs",
    "args": {
      "job_type": "웹디자이너",
      "salary_min": 4000,
      "location_query": "강남역",
      "max_commute_minutes": 30,
      "use_current_location": false
    }
  }
}
```

#### Step 6-7: Firestore Query

**Query:**
```python
db.collection("jobs")
  .where("is_active", "==", True)
  .stream()
```

**Result (샘플):**
```json
[
  {
    "id": "jk_12345678",
    "title": "웹디자이너",
    "company_name": "(주)테크컴퍼니",
    "location": "서울 강남구",
    "location_full": "서울특별시 강남구 역삼동 123-45",
    "salary_text": "4,500~5,500만원",
    "salary_min": 4500,
    "salary_max": 5500,
    "mvp_category": "디자인",
    "is_active": true
  },
  // ... ~1000건
]
```

#### Step 8-9: Stage 1 - 직무 필터 (AI)

**Gemini 입력:**
```
다음 채용공고 목록에서 "웹디자이너"에 해당하는 공고만 선별하세요.

## 후보 공고
[jk_12345678] 웹디자이너 (웹디자인/퍼블리싱)
[jk_12345679] UI/UX 디자이너 (디자인)
[jk_12345680] 백엔드 개발자 (개발)
...

## 응답 형식
["jk_123", "jk_456", ...]
```

**Gemini 출력:**
```json
["jk_12345678", "jk_12345679", "jk_12345681", ...]
```

**결과:** ~100건으로 축소

#### Step 10: Stage 2 - 연봉 필터 (로컬)

**필터 로직:**
```python
def filter_by_salary(jobs, salary_min=4000):
    result = []
    for job in jobs:
        job_salary = job.get("salary_min")
        if job_salary is None:  # 회사내규/협상가능
            result.append(job)
        elif job_salary >= salary_min:
            result.append(job)
    return result
```

**입력:** ~100건
**출력:** ~80건 (연봉 조건 충족 + 협상가능 포함)

#### Step 11-12: Stage 3 - 거리 필터 (Maps API)

**Maps API Request:**
```
GET https://maps.googleapis.com/maps/api/distancematrix/json
  ?origins=강남역
  &destinations=서울특별시 강남구 역삼동 123-45|서울특별시 종로구 ...
  &mode=transit
  &key=API_KEY
```

**Maps API Response:**
```json
{
  "rows": [{
    "elements": [
      {
        "status": "OK",
        "duration": {
          "value": 900,
          "text": "15분"
        }
      },
      {
        "status": "OK",
        "duration": {
          "value": 2400,
          "text": "40분"
        }
      }
    ]
  }]
}
```

**필터 결과:**
```python
# 30분 이내만 포함
filtered_jobs = [
    {**job, "travel_time_minutes": 15, "travel_time_text": "지하철 15분"}
    for job in jobs
    if travel_time <= 30
]
```

**입력:** ~80건
**출력:** ~20건 (30분 이내, 이동시간순 정렬)

#### Step 13-14: Function Response & AI 응답

**Function Response:**
```json
{
  "total_count": 18,
  "jobs": [
    {
      "id": "jk_12345678",
      "title": "웹디자이너",
      "company": "(주)테크컴퍼니",
      "location": "서울 강남구 역삼동",
      "salary": "4,500~5,500만원",
      "travel_time": "15분"
    }
  ]
}
```

**AI 최종 응답:**
```
강남역에서 30분 이내의 웹디자이너 공고 18건을 찾았어요!

가장 가까운 곳은 (주)테크컴퍼니의 웹디자이너 포지션으로,
강남역에서 지하철로 15분 거리에 있어요.
연봉은 4,500~5,500만원 수준입니다.
```

#### Step 15: API Response

**POST /chat Response:**
```json
{
  "success": true,
  "response": "강남역에서 30분 이내의 웹디자이너 공고 18건을 찾았어요! ...",
  "jobs": [
    {
      "id": "jk_12345678",
      "title": "웹디자이너",
      "company_name": "(주)테크컴퍼니",
      "location": "서울 강남구",
      "salary": "4,500~5,500만원",
      "experience": "경력 2년 이상",
      "employment_type": "정규직",
      "deadline": "상시",
      "url": "https://www.jobkorea.co.kr/Recruit/GI_Read/12345678",
      "travel_time_minutes": 15,
      "travel_time_text": "지하철 15분"
    },
    // ... 최대 20건
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_count": 18,
    "total_pages": 1,
    "has_next": false,
    "has_prev": false
  },
  "search_params": {
    "job_type": "웹디자이너",
    "salary_min": 4000,
    "location_query": "강남역",
    "max_commute_minutes": 30,
    "use_current_location": false,
    "user_coordinates": [37.497942, 127.027621]
  },
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## 3. GPS 기반 검색 플로우

### 3.1 현재 위치 검색 시나리오

**사용자 입력:**
```
"내 위치에서 30분 이내 프론트엔드 개발자, 연봉 무관"
```

**AI 파싱 결과:**
```json
{
  "job_type": "프론트엔드 개발자",
  "salary_min": 0,
  "location_query": "",
  "use_current_location": true,
  "max_commute_minutes": 30
}
```

**Stage 3 처리:**
```python
# GPS 좌표 직접 사용
if use_current_location and user_coordinates:
    origin = f"{user_coordinates[0]},{user_coordinates[1]}"
    # Maps API 호출 시 좌표 문자열로 전달
```

**Maps API Request:**
```
GET https://maps.googleapis.com/maps/api/distancematrix/json
  ?origins=37.497942,127.027621  # GPS 좌표
  &destinations=서울특별시 강남구 역삼동 123-45|...
  &mode=transit
```

---

## 4. 복수 조건 검색 플로우

### 4.1 복수 직무 검색

**사용자 입력:**
```
"개발자 아니면 디자이너, 연봉 무관"
```

**직무 파싱 (AI):**
```json
["개발자", "디자이너"]
```

**Stage 1 처리:**
```python
# 각 직무별로 필터 실행
results = {}
for job_type in ["개발자", "디자이너"]:
    filtered = await _filter_by_job_type(job_type, all_jobs)
    for job in filtered:
        results[job["id"]] = job  # 중복 제거

# 합집합 반환
return list(results.values())
```

### 4.2 복수 출발지 검색

**사용자 입력:**
```
"강남역이나 판교에서 30분 이내"
```

**위치 파싱 (AI):**
```json
["강남역", "판교"]
```

**Stage 3 처리:**
```python
# 각 출발지별로 필터 실행
all_matching = {}
for origin in ["강남역", "판교"]:
    filtered = await filter_by_distance(jobs, origin, max_minutes=30)
    for job in filtered:
        # 더 짧은 이동시간으로 업데이트
        if job["id"] not in all_matching:
            all_matching[job["id"]] = job
        elif job["travel_time_minutes"] < all_matching[job["id"]]["travel_time_minutes"]:
            all_matching[job["id"]] = job

# 이동시간순 정렬
return sorted(all_matching.values(), key=lambda x: x["travel_time_minutes"])
```

---

## 5. 크롤러 데이터 플로우

### 5.1 크롤링 시퀀스

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Crawler  │     │ JobKorea │     │Normalizer│     │Firestore │
└────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │                │
     │ 1. HTTP GET    │                │                │
     │───────────────>│                │                │
     │                │                │                │
     │ 2. HTML        │                │                │
     │<───────────────│                │                │
     │                │                │                │
     │ 3. Parse HTML  │                │                │
     │────────┐       │                │                │
     │        │       │                │                │
     │<───────┘       │                │                │
     │                │                │                │
     │ 4. Normalize   │                │                │
     │────────────────────────────────>│                │
     │                │                │                │
     │ 5. Normalized Data              │                │
     │<────────────────────────────────│                │
     │                │                │                │
     │ 6. MVP Filter  │                │                │
     │────────┐       │                │                │
     │        │       │                │                │
     │<───────┘       │                │                │
     │                │                │                │
     │ 7. Batch Save (500건씩)         │                │
     │────────────────────────────────────────────────>│
     │                │                │                │
     │ 8. Confirm     │                │                │
     │<────────────────────────────────────────────────│
```

### 5.2 HTML 파싱

**HTML 구조 (잡코리아):**
```html
<li class="devloopArea" data-info="12345678|company_id|...">
  <div class="description">
    <a href="/Recruit/GI_Read/12345678">
      <span class="text">웹디자이너</span>
    </a>
  </div>
  <div class="company">
    <span class="name">
      <a href="/...">(주)테크컴퍼니</a>
    </span>
  </div>
  <ul class="option">
    <li>서울 강남구</li>
    <li>경력 2년↑</li>
    <li>정규직</li>
    <li>4,500~5,500만원</li>
  </ul>
</li>
```

**파싱 결과:**
```json
{
  "id": "jk_12345678",
  "title": "웹디자이너",
  "company_name": "(주)테크컴퍼니",
  "location": "서울 강남구",
  "experience_type": "경력",
  "experience_min": 2,
  "employment_type": "정규직",
  "salary_text": "4,500~5,500만원",
  "url": "https://www.jobkorea.co.kr/Recruit/GI_Read/12345678"
}
```

### 5.3 정규화

**연봉 정규화 (`normalizers/salary.py`):**

| 입력 | salary_min | salary_max | salary_type |
|------|-----------|-----------|-------------|
| "4,500~5,500만원" | 4500 | 5500 | annual |
| "월 350~400만원" | 4200 | 4800 | monthly→annual |
| "협의" | null | null | negotiable |
| "회사 내규에 따름" | null | null | internal |

**직무 정규화 (`normalizers/job_type.py`):**

| 입력 | mvp_category | normalized |
|------|-------------|------------|
| "웹디자이너" | 디자인 | 웹디자이너 |
| "React 개발자" | 개발 | 프론트엔드 |
| "마케팅 매니저" | 마케팅 | 마케터 |

### 5.4 MVP 필터링

```python
MVP_CATEGORIES = {
    "개발": ["개발자", "developer", "engineer", "백엔드", "프론트엔드", ...],
    "디자인": ["디자이너", "designer", "ui", "ux", ...],
    "마케팅": ["마케터", "marketing", "광고", ...],
    "기획": ["기획자", "pm", "po", ...]
}

def get_mvp_category(title: str) -> Optional[str]:
    title_lower = title.lower()
    for category, keywords in MVP_CATEGORIES.items():
        if any(kw in title_lower for kw in keywords):
            return category
    return None
```

### 5.5 Firestore 저장

**Batch Write:**
```python
async def save_jobs(jobs: List[Dict]) -> Dict[str, int]:
    stats = {"new": 0, "updated": 0, "failed": 0}

    for batch_start in range(0, len(jobs), 500):
        batch = db.batch()
        batch_jobs = jobs[batch_start:batch_start + 500]

        for job in batch_jobs:
            doc_ref = db.collection("jobs").document(job["id"])
            batch.set(doc_ref, {
                **job,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "crawled_at": firestore.SERVER_TIMESTAMP
            }, merge=True)

        await batch.commit()

    return stats
```

---

## 6. 페이지네이션 플로우

### 6.1 초기 검색

**Request:**
```json
{
  "message": "웹디자이너 연봉 무관",
  "page": 1,
  "page_size": 20
}
```

**Response:**
```json
{
  "jobs": [/* 1-20번째 공고 */],
  "pagination": {
    "page": 1,
    "total_count": 85,
    "total_pages": 5,
    "has_next": true
  }
}
```

### 6.2 추가 로드 (더 보기)

**Request:**
```json
{
  "message": "",
  "conversation_id": "existing-id",
  "page": 2,
  "page_size": 20
}
```

**Backend 처리:**
```python
# 대화 히스토리에서 이전 검색 결과 유지
# Stage 1-3 다시 실행하지 않음
# 캐시된 final_jobs에서 페이지네이션만 적용

start_idx = (page - 1) * page_size  # 20
end_idx = start_idx + page_size     # 40
page_jobs = final_jobs[start_idx:end_idx]
```

**Response:**
```json
{
  "jobs": [/* 21-40번째 공고 */],
  "pagination": {
    "page": 2,
    "total_count": 85,
    "total_pages": 5,
    "has_next": true,
    "has_prev": true
  }
}
```

---

## 7. 에러 플로우

### 7.1 Gemini API 오류

```
사용자 → Backend → Gemini API (오류)
                 ↓
             예외 캐치
                 ↓
             에러 응답 반환
```

**Response:**
```json
{
  "success": false,
  "response": "죄송합니다. 처리 중 오류가 발생했습니다. 다시 시도해주세요.",
  "jobs": [],
  "error": "Gemini API error: quota exceeded"
}
```

### 7.2 Maps API 불가

```
Stage 3 → Maps API (unavailable)
       ↓
   is_available() = false
       ↓
   Stage 3 스킵, Stage 2 결과 그대로 반환
```

**Response (위치 필터 없이):**
```json
{
  "jobs": [/* Stage 2 결과 그대로 */],
  "search_params": {
    "location_query": "강남역",
    // travel_time_* 필드 없음
  }
}
```

### 7.3 Firestore 연결 실패

```
Backend → Firestore (connection error)
       ↓
   더미 데이터 반환 (개발 환경)
   또는
   에러 응답 (프로덕션)
```

---

## 8. 데이터 타입 정의

### 8.1 TypeScript (Frontend)

```typescript
// types/index.ts

interface Coordinates {
  latitude: number;
  longitude: number;
}

interface Job {
  id: string;
  title: string;
  company_name: string;
  location: string;
  salary: string;
  experience: string;
  employment_type: string;
  deadline: string;
  url: string;
  travel_time_minutes?: number;
  travel_time_text?: string;
}

interface PaginationInfo {
  page: number;
  page_size: number;
  total_count: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

interface ChatRequest {
  message: string;
  conversation_id?: string;
  page?: number;
  page_size?: number;
  user_lat?: number;
  user_lng?: number;
}

interface ChatResponse {
  success: boolean;
  response: string;
  jobs: Job[];
  pagination: PaginationInfo;
  search_params?: SearchParams;
  conversation_id?: string;
  error?: string;
}

interface SearchParams {
  job_type?: string;
  salary_min?: number;
  location_query?: string;
  max_commute_minutes?: number;
  use_current_location?: boolean;
  user_coordinates?: [number, number];
}
```

### 8.2 Python (Backend)

```python
# models/schemas.py

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    conversation_id: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    user_lat: Optional[float] = Field(None, ge=-90, le=90)
    user_lng: Optional[float] = Field(None, ge=-180, le=180)

class JobItem(BaseModel):
    id: str
    title: str
    company_name: str
    location: str
    salary: Optional[str]
    experience: Optional[str]
    employment_type: Optional[str]
    deadline: Optional[str]
    url: str
    travel_time_minutes: Optional[int]
    travel_time_text: Optional[str]

class PaginationInfo(BaseModel):
    page: int
    page_size: int
    total_count: int
    total_pages: int
    has_next: bool
    has_prev: bool

class SearchParams(BaseModel):
    job_type: Optional[str]
    salary_min: Optional[int]
    location_query: Optional[str]
    max_commute_minutes: Optional[int]
    use_current_location: Optional[bool]
    user_coordinates: Optional[Tuple[float, float]]

class ChatResponse(BaseModel):
    success: bool
    response: str
    jobs: List[JobItem]
    pagination: PaginationInfo
    search_params: Optional[SearchParams]
    conversation_id: Optional[str]
    error: Optional[str]
```

### 8.3 Firestore Document

```python
# Firestore jobs collection document

{
    # 기본 정보
    "id": "jk_12345678",
    "title": "웹디자이너",
    "company_name": "(주)테크컴퍼니",
    "url": "https://www.jobkorea.co.kr/Recruit/GI_Read/12345678",
    "source": "jobkorea",

    # 위치
    "location": "서울 강남구",
    "location_full": "서울특별시 강남구 역삼동 123-45",

    # 연봉
    "salary_text": "4,500~5,500만원",
    "salary_min": 4500,
    "salary_max": 5500,

    # 경력/고용
    "experience_type": "경력",
    "experience_min": 2,
    "experience_max": None,
    "employment_type": "정규직",

    # 기타
    "deadline": "상시",
    "job_type_raw": "웹디자인/퍼블리싱",
    "mvp_category": "디자인",

    # 상태
    "is_active": True,
    "created_at": Timestamp,
    "updated_at": Timestamp,
    "crawled_at": Timestamp
}
```

---

## 9. 캐싱 전략

### 9.1 현재 캐싱

| 데이터 | 캐시 위치 | TTL |
|--------|----------|-----|
| 대화 히스토리 | 메모리 (GeminiService) | 세션 동안 |
| GPS 좌표 | 브라우저 (useGeolocation) | 1분 |
| 검색 결과 | 없음 (매번 조회) | - |

### 9.2 향후 개선 예정

| 데이터 | 캐시 전략 | 예상 효과 |
|--------|----------|----------|
| 전체 활성 공고 | Redis, 5분 TTL | DB 부하 감소 |
| Maps API 결과 | Redis, 1시간 TTL | API 비용 절감 |
| AI 직무 필터 결과 | Redis, 10분 TTL | 응답 시간 개선 |
