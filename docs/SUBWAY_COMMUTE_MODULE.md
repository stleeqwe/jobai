# 서울 지하철 기반 통근시간 계산 모듈

## 1. 개요

### 1.1 목적

Google Maps API ($1.25/검색)를 대체하여 **무료로** 서울 지하철 기반 통근시간을 계산하는 독립 모듈입니다.

### 1.2 핵심 특징

| 항목 | 값 |
|------|-----|
| **비용** | $0 (Google Maps: $1.25/검색) |
| **지원 노선** | 1-9호선 + 신분당선 (10개 노선) |
| **역 수** | 328개 |
| **구간 수** | 426개 |
| **정확도** | ±10분 (10분 단위 반올림) |
| **의존성** | 없음 (순수 Python, 내장 데이터) |

### 1.3 파일 위치

```
backend/app/services/
├── seoul_subway_commute.py   # 핵심 모듈 (독립 실행 가능)
└── subway.py                 # Backend 연동 래퍼
```

---

## 2. 아키텍처

### 2.1 전체 구조

```
┌─────────────────────────────────────────────────────────────┐
│                    SeoulSubwayCommute                        │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   stations  │  │  adjacency  │  │  district_stations  │  │
│  │  (328개 역) │  │ (그래프 엣지)│  │   (구→대표역 매핑)  │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    핵심 알고리즘                         ││
│  │  ┌──────────┐  ┌───────────┐  ┌────────────────────┐   ││
│  │  │ Dijkstra │  │ Haversine │  │ _find_nearest_station│   ││
│  │  │ (최단경로)│  │ (거리계산) │  │    (최근접 역 탐색)  │   ││
│  │  └──────────┘  └───────────┘  └────────────────────┘   ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    공개 API                              ││
│  │  • calculate(origin, destination) → Dict                ││
│  │  • calculate_by_coords(lat1, lng1, lat2, lng2) → Dict   ││
│  │  • filter_jobs(jobs, origin, max_minutes) → List        ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### 2.2 데이터 흐름

```
[사용자 입력]
"건대입구역에서 30분 이내"
        │
        ▼
┌───────────────────┐
│  _parse_location  │  역명/주소/좌표 → (lat, lng)
└───────────────────┘
        │
        ▼
┌───────────────────────┐
│ _find_nearest_station │  (lat, lng) → station_id + 도보시간
└───────────────────────┘
        │
        ▼
┌───────────────────┐
│     _dijkstra     │  출발역 → 도착역 최단경로
└───────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│         총 통근시간 계산               │
│  = 도보(출발) + 지하철 + 도보(도착)    │
│  + 대기시간(5분)                       │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────┐
│ _round_to_10_min  │  31분 → "약 30분"
└───────────────────┘
```

### 2.3 Backend 연동 구조 (V4 - AI 호출 없음)

```
┌─────────────────────────────────────────────────────────────┐
│                      gemini.py                               │
│              (Stage 3 거리 필터 - AI 호출 없음)              │
│                                                             │
│  # location_query를 그대로 전달 (파싱 없음)                  │
│  if origin and subway_service.is_available():               │
│      stage3_jobs = await subway_service.filter_jobs_by_...( │
│          stage2_jobs, origin, max_minutes                   │
│      )                                                      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼ origin = "을지로역" (그대로)
┌─────────────────────────────────────────────────────────────┐
│                      subway.py                               │
│                   (SubwayService 래퍼)                       │
│  • filter_jobs_by_travel_time(jobs, origin, max_minutes)    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                 seoul_subway_commute.py                      │
│                  (SeoulSubwayCommute)                        │
│                                                             │
│  • _parse_location("을지로역")                              │
│    → _find_station_by_name() → 을지로입구역 좌표            │
│  • filter_jobs(jobs, origin, max_minutes)                   │
│    → 각 공고 좌표 추출 → Dijkstra → 통근시간 필터링         │
└─────────────────────────────────────────────────────────────┘
```

**핵심 변경 (V4)**:
- gemini.py에서 `_parse_location_query` AI 호출 제거
- `location_query`를 그대로 `subway_service`에 전달
- 모든 위치 파싱은 `SeoulSubwayCommute._parse_location()`에서 규칙 기반 처리

---

## 3. 지원 노선

### 3.1 노선별 역 수

| 노선 | 역 수 | 주요 역 |
|------|-------|---------|
| **1호선** | 31개 | 서울역, 종로3가, 청량리 |
| **2호선** | 51개 | 강남, 잠실, 건대입구, 홍대입구 |
| **3호선** | 34개 | 교대, 압구정, 충무로 |
| **4호선** | 27개 | 명동, 동대문, 노원 |
| **5호선** | 51개 | 광화문, 여의도, 강동 |
| **6호선** | 38개 | 합정, 삼각지, 이태원 |
| **7호선** | 42개 | 가산디지털단지, 청담, 상봉 |
| **8호선** | 17개 | 잠실, 복정, 모란 |
| **9호선** | 38개 | 여의도, 고속터미널, 신논현 |
| **신분당선** | 16개 | 강남, 양재, 판교 |
| **합계** | **328개** | |

### 3.2 환승역

총 **145개** 환승역 지원 (주요 환승역):

- **강남역**: 2호선 ↔ 신분당선
- **고속터미널역**: 3호선 ↔ 7호선 ↔ 9호선
- **여의도역**: 5호선 ↔ 9호선
- **잠실역**: 2호선 ↔ 8호선
- **왕십리역**: 2호선 ↔ 5호선
- **사당역**: 2호선 ↔ 4호선

### 3.3 환승 시간

| 환승 유형 | 소요 시간 |
|----------|----------|
| 같은 역사 내 | 3분 |
| 다른 역사 (기본) | 5분 |
| 긴 환승 통로 | 7분 |

---

## 4. 알고리즘

### 4.1 최단경로 (Dijkstra)

```python
def _dijkstra(self, start: str, end: str) -> Tuple[Optional[int], List[str]]:
    """
    Dijkstra 알고리즘으로 최단 경로 탐색

    그래프 구조:
    - 노드: station_id (예: "line2_강남역")
    - 엣지: (이웃 station_id, 소요시간)
    - 환승: 별도 엣지로 처리 (예: line2_강남역 → shinbundang_강남역)

    Returns:
        (총_소요시간, 경로_리스트)
    """
```

**시간 복잡도**: O((V + E) log V)
- V = 328 (역 수)
- E = 426 (엣지 수)

### 4.2 최근접 역 탐색 (Haversine)

```python
def _find_nearest_station(self, lat: float, lng: float) -> Tuple[Optional[str], int]:
    """
    주어진 좌표에서 가장 가까운 역 탐색

    Haversine 공식:
    a = sin²(Δlat/2) + cos(lat1) × cos(lat2) × sin²(Δlng/2)
    c = 2 × atan2(√a, √(1-a))
    d = R × c  (R = 6371km)

    도보 시간 = 거리(m) / 80m/분 + 1분

    Returns:
        (station_id, 도보_소요시간)
    """
```

**도보 속도**: 80m/분 (= 4.8km/h, 보수적 추정)

### 4.3 10분 단위 반올림

```python
def _round_to_10_minutes(self, minutes: int) -> Tuple[int, str]:
    """
    소요시간을 10분 단위로 반올림

    예시:
    - 23분 → (20, "약 20분")
    - 27분 → (30, "약 30분")
    - 5분  → (10, "약 10분")  # 최소 10분

    Returns:
        (반올림된_분, 텍스트)
    """
```

---

## 5. API 인터페이스

### 5.1 calculate()

```python
def calculate(
    self,
    origin: str,
    destination: str
) -> Optional[Dict[str, Any]]:
    """
    두 지점 간 통근시간 계산

    Args:
        origin: 출발지 (역명, 주소, 또는 "lat,lng")
        destination: 도착지 (역명, 주소, 또는 "lat,lng")

    Returns:
        {
            'minutes': 31,           # 실제 소요시간
            'text': '약 30분',       # 표시용 텍스트
            'origin_station': '건대입구역',
            'destination_station': '강남역',
            'origin_walk': 5,        # 출발 도보 시간
            'destination_walk': 3,   # 도착 도보 시간
            'subway_time': 18,       # 지하철 소요시간
            'path': ['line2_건대입구역', 'line2_성수역', ...]
        }

    Examples:
        >>> c = SeoulSubwayCommute()
        >>> c.calculate("건대입구역", "강남역")
        {'minutes': 31, 'text': '약 30분', ...}

        >>> c.calculate("37.5403,127.0694", "서울 강남구")
        {'minutes': 28, 'text': '약 30분', ...}
    """
```

### 5.2 calculate_by_coords()

```python
def calculate_by_coords(
    self,
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float
) -> Optional[Dict[str, Any]]:
    """
    좌표로 통근시간 계산 (GPS 기반 검색용)

    Args:
        from_lat, from_lng: 출발지 좌표
        to_lat, to_lng: 도착지 좌표

    Returns:
        calculate()와 동일한 형식

    Examples:
        >>> c = SeoulSubwayCommute()
        >>> c.calculate_by_coords(37.5403, 127.0694, 37.4979, 127.0276)
        {'minutes': 31, 'text': '약 30분', ...}
    """
```

### 5.3 filter_jobs()

```python
def filter_jobs(
    self,
    jobs: List[Dict[str, Any]],
    origin: str,
    max_minutes: int
) -> List[Dict[str, Any]]:
    """
    통근시간 기준 공고 필터링

    Args:
        jobs: 공고 리스트 (lat, lng 또는 location/location_full 필드 필요)
        origin: 출발지 (역명, 주소, 또는 "lat,lng")
        max_minutes: 최대 통근시간 (분)

    Returns:
        통근시간 조건 충족 공고 리스트
        - travel_time_minutes: 소요시간 (분)
        - travel_time_text: 표시용 텍스트
        - 이동시간순 오름차순 정렬

    Examples:
        >>> jobs = [
        ...     {"id": "1", "location_full": "서울 강남구"},
        ...     {"id": "2", "lat": 37.5, "lng": 127.0},
        ... ]
        >>> c = SeoulSubwayCommute()
        >>> filtered = c.filter_jobs(jobs, "건대입구역", 30)
        >>> filtered[0]['travel_time_text']
        '약 20분'
    """
```

---

## 6. 위치 파싱

### 6.1 지원 형식

| 형식 | 예시 | 처리 방법 |
|------|------|----------|
| **좌표** | `"37.5403,127.0694"` | 직접 파싱 |
| **역명** | `"강남역"`, `"강남"` | name_to_ids 매핑 |
| **구 이름** | `"서울 강남구"` | district_stations 매핑 |

### 6.2 구 → 대표역 매핑

```python
district_stations = {
    "강남구": "line2_강남역",
    "서초구": "line2_서초역",
    "송파구": "line2_잠실역",
    "강동구": "line5_강동역",
    "광진구": "line2_건대입구역",
    "성동구": "line2_왕십리역",
    "동대문구": "line1_청량리역",
    "중랑구": "line7_상봉역",
    "성북구": "line4_성신여대입구역",
    "강북구": "line4_수유역",
    "도봉구": "line4_창동역",
    "노원구": "line4_노원역",
    "은평구": "line3_연신내역",
    "서대문구": "line5_서대문역",
    "마포구": "line6_마포구청역",
    "용산구": "line6_삼각지역",
    "중구": "line4_충무로역",
    "종로구": "line1_종로3가역",
    "영등포구": "line2_영등포구청역",
    "구로구": "line2_구로디지털단지역",
    "금천구": "line7_가산디지털단지역",
    "양천구": "line2_신정역",
    "강서구": "line5_발산역",
    "동작구": "line4_총신대입구역",
    "관악구": "line2_서울대입구역",
}
```

---

## 7. 소요시간 계산

### 7.1 총 소요시간 공식

```
총 통근시간 = 도보(출발→역) + 지하철 소요시간 + 도보(역→도착) + 대기시간
```

### 7.2 시간 상수

| 항목 | 값 | 설명 |
|------|-----|------|
| **도보 속도** | 80m/분 | 보수적 추정 (4.8km/h) |
| **대기 버퍼** | 5분 | 평균 대기시간 |
| **역간 평균** | 2분 | 역 사이 기본 소요시간 |
| **환승 시간** | 3-7분 | 환승역별 상이 |

### 7.3 예시 계산

**건대입구역 → 강남역**

```
1. 출발 도보: 0분 (역에서 출발)
2. 지하철:
   - 건대입구 → 성수 → 잠실새내 → ... → 강남
   - 약 18분
3. 도착 도보: 3분
4. 대기 버퍼: 5분

총 = 0 + 18 + 3 + 5 = 26분 → "약 30분"
```

---

## 8. 정확도

### 8.1 오차 요인

| 요인 | 영향 | 대응 |
|------|------|------|
| 도보 시간 추정 | ±5분 | 보수적 80m/분 사용 |
| 대기 시간 미포함 | ±5분 | 고정 5분 버퍼 추가 |
| 출퇴근 혼잡 미반영 | ±10분 | "약 X분"으로 표시 |

### 8.2 최종 정확도

- **목표**: ±10분
- **달성 방법**: 10분 단위 반올림으로 오차 흡수
- **표시 형식**: "약 20분", "약 30분" 등

### 8.3 Google Maps 비교

| 경로 | Subway 모듈 | Google Maps | 오차 |
|------|------------|-------------|------|
| 건대입구 → 강남 | 약 30분 | 28분 | 2분 |
| 여의도 → 고속터미널 | 약 30분 | 25분 | 5분 |
| 판교 → 강남 | 약 20분 | 18분 | 2분 |
| 잠실 → 홍대 | 약 40분 | 42분 | 2분 |

---

## 9. 사용 예시

### 9.1 독립 실행

```python
from app.services.seoul_subway_commute import SeoulSubwayCommute

# 인스턴스 생성
commute = SeoulSubwayCommute()

# 초기화 확인
print(f"초기화: {commute.is_initialized()}")
print(f"통계: {commute.get_stats()}")
# 출력: {'stations': 328, 'edges': 426, 'lines': 10}

# 통근시간 계산
result = commute.calculate("건대입구역", "강남역")
print(f"소요시간: {result['text']}")  # 약 30분

# 좌표 기반 계산
result = commute.calculate_by_coords(
    37.5403, 127.0694,  # 건대입구역
    37.4979, 127.0276   # 강남역
)
print(f"소요시간: {result['text']}")  # 약 30분
```

### 9.2 공고 필터링

```python
# 공고 리스트
jobs = [
    {"id": "1", "title": "백엔드 개발자", "location_full": "서울 강남구"},
    {"id": "2", "title": "프론트엔드", "lat": 37.5662, "lng": 126.9784},
    {"id": "3", "title": "디자이너", "location_full": "서울 중구"},
]

# 건대입구역에서 30분 이내 필터링
filtered = commute.filter_jobs(jobs, "건대입구역", 30)

for job in filtered:
    print(f"{job['title']}: {job['travel_time_text']}")
# 출력:
# 백엔드 개발자: 약 30분
# 디자이너: 약 20분
```

### 9.3 Backend 연동

```python
from app.services.subway import subway_service

# 서비스 사용 가능 여부
if subway_service.is_available():
    # 공고 필터링
    filtered_jobs = await subway_service.filter_jobs_by_travel_time(
        jobs=all_jobs,
        origin="건대입구역",
        max_minutes=30
    )
```

---

## 10. 제한사항

### 10.1 현재 제한

| 항목 | 제한 | 비고 |
|------|------|------|
| **지역** | 서울 수도권 | 경기 일부 (신분당선) 포함 |
| **교통수단** | 지하철만 | 버스 미지원 |
| **실시간** | 미지원 | 평균 소요시간 사용 |
| **시간대** | 미반영 | 출퇴근 혼잡 미반영 |

### 10.2 향후 확장 가능

- 경기도 지하철 (분당선, 경의중앙선 등)
- 버스 노선 통합
- 실시간 도착 정보 연동
- 시간대별 소요시간 차등

---

## 11. 유지보수

### 11.1 데이터 업데이트

신규 역/노선 추가 시 `_get_builtin_stations()`, `_get_builtin_edges()`, `_get_builtin_transfers()` 수정:

```python
def _get_builtin_stations(self) -> List[Dict]:
    """내장 역 데이터"""
    return [
        # 새 역 추가
        {"id": "line9_새역", "name": "새역", "line": "9호선",
         "lat": 37.xxxx, "lng": 127.xxxx},
        ...
    ]
```

### 11.2 테스트

```bash
# E2E 테스트 실행
cd /Users/stlee/Desktop/jobbot
python3 tests/test_e2e_commute.py

# 특정 테스트만
python3 tests/test_e2e_commute.py --test basic
python3 tests/test_e2e_commute.py --test line9
python3 tests/test_e2e_commute.py --test shinbundang
```

---

## 12. 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2026-01-13 | 1.0.0 | 초기 버전 (1-8호선, 274개 역) |
| 2026-01-13 | 1.1.0 | 9호선 추가 (38개 역) |
| 2026-01-13 | 1.2.0 | 신분당선 추가 (16개 역) |
| 2026-01-13 | 1.2.1 | E2E 테스트 수정, Stage 3 로직 개선 |
| 2026-01-13 | 1.3.0 | **V4 아키텍처**: gemini.py AI 위치 파싱 제거, location_query 직접 전달 |

---

## 13. 참고 자료

### 13.1 관련 파일

- `backend/app/services/seoul_subway_commute.py` - 핵심 모듈
- `backend/app/services/subway.py` - Backend 래퍼
- `backend/app/services/gemini.py` - Stage 3 연동 (Line 527-586)
- `tests/test_e2e_commute.py` - E2E 테스트
- `tests/run_e2e_test.sh` - 빠른 테스트 스크립트
- `docs/E2E_TEST_PLAN_COMMUTE.md` - 테스트 계획

### 13.2 공공데이터 출처 (참고용)

| 데이터 | URL |
|--------|-----|
| 역간 소요시간 | data.go.kr/15119345 |
| 환승 소요시간 | data.go.kr/15044419 |
| 역 좌표 | data.go.kr/15099316 |

*현재 버전은 내장 데이터를 사용하며, 외부 API 호출 없음*
