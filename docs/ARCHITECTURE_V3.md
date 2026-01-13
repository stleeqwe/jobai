# JobChat 아키텍처 V3: 3-Stage Sequential Filter with Maps API

## 개요

기존 V2 아키텍처의 한계를 해결하기 위한 새로운 설계

### V2의 문제점

| 문제 | 원인 |
|------|------|
| 위치 필터 실패 | "을지로역" → "중구" 수동 매핑 불가능 |
| 직무 매칭 실패 | AI가 "프론트 앱 개발자"와 "웹디자이너" 혼동 |
| 연봉 필터 실패 | 대부분 공고가 `salary_min=None` |
| 불완전한 검색 | 필수 조건 없이도 검색 시도 |

### V3 핵심 원칙

```
1. 필수 정보 수집: 직무, 연봉, 지역 - 3가지 없으면 검색 안함
2. 직무 우선 필터: AI가 의미적으로 직무 매칭
3. 연봉 유연 필터: 회사내규/협상가능 포함
4. 지도 API 거리 계산: 실제 이동시간 기반 필터링
```

---

## 아키텍처 흐름

```
┌─────────────────────────────────────────────────────────────┐
│                      사용자 입력                              │
│  "을지로역 30분 거리, 프론트 앱 개발자, 연봉 5천 이상"           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 Phase 0: 필수 정보 수집                       │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                      │
│  │  직무   │  │  연봉   │  │  지역   │  ← 3가지 필수         │
│  └─────────┘  └─────────┘  └─────────┘                      │
│  미입력 시 AI가 친절하게 추가 질문                             │
└─────────────────────────────────────────────────────────────┘
                              │ 3가지 모두 수집됨
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 Stage 1: 직무 필터 (AI)                       │
│                                                              │
│  입력: 전체 활성 공고 (~1000건)                               │
│  처리: AI가 "프론트 앱 개발자"에 해당하는 공고 선별             │
│        - Flutter, React Native, iOS, Android 앱 개발          │
│        - 웹 프론트엔드, 디자이너는 제외                        │
│  출력: 직무 매칭 공고 (~100건)                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 Stage 2: 연봉 필터 (DB)                       │
│                                                              │
│  조건: salary_min >= 요청값 OR salary_min IS NULL             │
│        (NULL = 회사내규, 협상가능 포함)                        │
│  출력: 연봉 조건 충족 공고 (~80건)                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 Stage 3: 지역 필터 (Maps API)                 │
│                                                              │
│  입력: 사용자 위치 "을지로역", 조건 "30분 이내"                │
│  처리:                                                       │
│    1. 각 공고의 location_full 주소 추출                       │
│    2. 주소 없는 공고 제외                                     │
│    3. Google Maps Distance Matrix API 호출                   │
│    4. 이동시간 30분 이내 공고만 선택                          │
│  출력: 최종 결과 (~20건)                                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 결과 반환 + 페이지네이션                       │
│  - 이동시간순 정렬                                            │
│  - 20건/페이지                                               │
│  - 각 공고에 예상 이동시간 표시                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 0: 필수 정보 수집

### AI 가이드 프롬프트

```
사용자가 채용공고를 찾으면, 반드시 다음 3가지 정보를 수집해야 합니다:

1. 직무 (job_type): 어떤 일을 하고 싶은지
   - 예: "프론트엔드 개발자", "iOS 앱 개발", "백엔드 엔지니어"

2. 연봉 (salary_requirement): 희망 연봉 조건
   - 예: "5천만원 이상", "협상 가능", "상관없음"

3. 지역 (location_requirement): 근무지 조건
   - 예: "강남역 근처", "을지로에서 30분 이내", "판교"

3가지 중 하나라도 없으면:
- 친절하게 추가 질문
- "어떤 직무를 찾으시나요?" / "희망 연봉이 있으신가요?" / "어느 지역에서 일하고 싶으신가요?"

3가지 모두 수집되면:
- search_jobs 함수 호출
```

### 수집 예시

```
사용자: "개발자 채용공고 찾아줘"
AI: "어떤 개발자를 찾으시나요? (예: 백엔드, 프론트엔드, 앱 개발 등)
     그리고 희망하시는 연봉과 근무 지역도 알려주시면 더 정확하게 찾아드릴게요!"

사용자: "프론트 앱 개발, 연봉 5천 이상, 을지로역 근처"
AI: [search_jobs 함수 호출]
```

---

## Stage 1: 직무 필터 (AI 의미적 매칭)

### Function Definition

```python
SEARCH_JOBS_FUNCTION = FunctionDeclaration(
    name="search_jobs",
    description="3가지 필수 조건(직무, 연봉, 지역)으로 채용공고 검색",
    parameters={
        "type": "object",
        "properties": {
            "job_type": {
                "type": "string",
                "description": "찾는 직무 (예: 'iOS 앱 개발자', '백엔드 엔지니어')"
            },
            "salary_min": {
                "type": "integer",
                "description": "최소 연봉 (만원 단위). 0이면 조건 없음"
            },
            "user_location": {
                "type": "string",
                "description": "사용자 출발 위치 (예: '을지로역', '강남역')"
            },
            "max_commute_minutes": {
                "type": "integer",
                "description": "최대 통근시간 (분). 기본 60분"
            }
        },
        "required": ["job_type", "salary_min", "user_location"]
    }
)
```

### AI 직무 매칭 프롬프트

```
다음 채용공고 목록에서 "{job_type}"에 해당하는 공고만 선별하세요.

## 선별 기준
- 직무가 정확히 일치하거나 밀접하게 관련된 공고만 선택
- 예시:
  - "프론트 앱 개발자" 요청 시:
    ✅ Flutter 개발자, React Native 개발자, iOS 개발자, Android 개발자
    ❌ 웹 프론트엔드, UI/UX 디자이너, 백엔드 개발자
  - "백엔드 개발자" 요청 시:
    ✅ Java 백엔드, Node.js 개발자, Python 서버 개발
    ❌ 프론트엔드, 앱 개발, 데브옵스

## 후보 공고
{candidates}

## 응답 형식
선별된 공고 ID를 JSON 배열로 반환:
["jk_123", "jk_456", ...]
```

---

## Stage 2: 연봉 필터

### 필터 로직

```python
def filter_by_salary(jobs: List[Dict], salary_min: int) -> List[Dict]:
    """
    연봉 조건 필터링

    포함 조건:
    - salary_min >= 요청값
    - salary_min IS NULL (회사내규, 협상가능)

    제외 조건:
    - salary_min < 요청값 (명시적으로 낮은 연봉)
    """
    if salary_min == 0:
        return jobs  # 조건 없음

    result = []
    for job in jobs:
        job_salary = job.get("salary_min")
        if job_salary is None:  # 회사내규, 협상가능
            result.append(job)
        elif job_salary >= salary_min:
            result.append(job)
        # else: 명시적으로 낮은 연봉은 제외

    return result
```

---

## Stage 3: 지역 필터 (Maps API)

### Google Maps Distance Matrix API

```python
async def filter_by_distance(
    jobs: List[Dict],
    user_location: str,
    max_minutes: int
) -> List[Dict]:
    """
    Google Maps API로 실제 이동시간 계산

    Args:
        jobs: Stage 2 결과
        user_location: 사용자 출발 위치 (예: "을지로역")
        max_minutes: 최대 통근시간 (분)

    Returns:
        이동시간 조건 충족 공고 (이동시간 정보 포함)
    """
    # 주소 없는 공고 제외
    jobs_with_address = [j for j in jobs if j.get("location_full")]

    # 목적지 주소 목록
    destinations = [j["location_full"] for j in jobs_with_address]

    # Google Maps API 호출 (배치)
    travel_times = await google_maps_distance_matrix(
        origin=user_location,
        destinations=destinations,
        mode="transit"  # 대중교통
    )

    # 조건 충족 공고 필터링
    result = []
    for job, travel_time in zip(jobs_with_address, travel_times):
        if travel_time and travel_time <= max_minutes:
            job["travel_time_minutes"] = travel_time
            result.append(job)

    # 이동시간순 정렬
    result.sort(key=lambda x: x.get("travel_time_minutes", 999))

    return result
```

### API 호출 최적화

```python
# Distance Matrix API는 한 번에 최대 25개 목적지 처리
# 100건 → 4번 API 호출

BATCH_SIZE = 25

async def google_maps_distance_matrix(origin: str, destinations: List[str], mode: str) -> List[int]:
    results = []

    for i in range(0, len(destinations), BATCH_SIZE):
        batch = destinations[i:i + BATCH_SIZE]
        response = await maps_client.distance_matrix(
            origins=[origin],
            destinations=batch,
            mode=mode
        )

        for element in response["rows"][0]["elements"]:
            if element["status"] == "OK":
                duration_seconds = element["duration"]["value"]
                results.append(duration_seconds // 60)
            else:
                results.append(None)  # 경로 없음

    return results
```

---

## 응답 형식

```json
{
  "success": true,
  "response": "을지로역에서 30분 이내 프론트 앱 개발자 공고 15건을 찾았어요!",
  "jobs": [
    {
      "id": "jk_123",
      "title": "Flutter 앱 개발자",
      "company_name": "테크스타트업",
      "location": "서울 중구 을지로3가",
      "salary": "5,000~7,000만원",
      "travel_time_minutes": 5,
      "travel_time_text": "도보 5분"
    },
    {
      "id": "jk_456",
      "title": "React Native 개발자",
      "company_name": "모바일앱스",
      "location": "서울 종로구 종로3가",
      "salary": "회사 내규에 따름",
      "travel_time_minutes": 12,
      "travel_time_text": "지하철 12분"
    }
  ],
  "pagination": {
    "page": 1,
    "total_count": 15,
    "has_next": false
  },
  "search_params": {
    "job_type": "프론트 앱 개발자",
    "salary_min": 5000,
    "user_location": "을지로역",
    "max_commute_minutes": 30
  }
}
```

---

## 구현 파일

| 파일 | 변경 내용 |
|------|----------|
| `backend/app/services/gemini.py` | Phase 0 가이드 + Stage 1 직무 필터 |
| `backend/app/services/job_search.py` | Stage 2 연봉 필터 |
| `backend/app/services/maps.py` | Stage 3 Maps API 연동 (신규) |
| `backend/app/models/schemas.py` | 응답 스키마 업데이트 |
| `backend/app/config.py` | GOOGLE_MAPS_API_KEY 추가 |

---

## 환경 설정

```bash
# backend/.env
GOOGLE_MAPS_API_KEY=your_api_key_here
```

---

## 변경 이력

- **2026-01-13**: V3 아키텍처 설계 (3-Stage Sequential Filter with Maps API)
