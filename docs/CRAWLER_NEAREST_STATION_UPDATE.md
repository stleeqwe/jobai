# 크롤러 nearest_station 필드 추가 작업

## 개요

크롤링 시 각 채용공고의 **가장 가까운 지하철역**과 **도보 시간**을 계산하여 저장.
이 필드는 V6 아키텍처에서 통근시간 계산의 핵심 데이터.

---

## 1. 추가할 필드

| 필드 | 타입 | 설명 | 예시 |
|------|------|------|------|
| `nearest_station` | string | 가장 가까운 지하철역 이름 | "역삼역" |
| `station_walk_minutes` | int | 해당 역까지 도보 시간 (분) | 8 |

---

## 2. 의존성

`backend/app/services/seoul_subway_commute.py` 모듈을 크롤러에서 사용해야 함.

### 해결 방법: 모듈 복사

```bash
# 백엔드의 지하철 모듈을 크롤러로 복사
cp backend/app/services/seoul_subway_commute.py crawler/app/services/
```

### 크롤러 디렉토리 구조 (수정 후)

```
crawler/
├── app/
│   ├── scrapers/
│   │   └── jobkorea.py      # 수정 대상
│   ├── services/            # 신규 디렉토리
│   │   ├── __init__.py      # 신규
│   │   └── seoul_subway_commute.py  # 복사
│   ├── normalizers/
│   ├── db/
│   └── ...
```

---

## 3. 수정 파일

### 3.1 `crawler/app/services/__init__.py` (신규)

```python
"""크롤러 서비스 모듈"""

from .seoul_subway_commute import SeoulSubwayCommute

__all__ = ["SeoulSubwayCommute"]
```

### 3.2 `crawler/app/scrapers/jobkorea.py` (수정)

#### 3.2.1 import 추가 (파일 상단)

```python
# 기존 import들 아래에 추가
from app.services.seoul_subway_commute import SeoulSubwayCommute

# 모듈 레벨에서 초기화 (크롤러 시작 시 1회)
_subway_module = None

def _get_subway_module():
    """지하철 모듈 lazy 초기화"""
    global _subway_module
    if _subway_module is None:
        try:
            _subway_module = SeoulSubwayCommute()
        except Exception as e:
            print(f"[Crawler] 지하철 모듈 초기화 실패: {e}")
    return _subway_module
```

#### 3.2.2 `_fetch_detail_info` 메서드 수정

`_fetch_detail_info` 메서드의 return문 직전에 다음 코드 추가:

```python
async def _fetch_detail_info(
    self, client: httpx.AsyncClient, job_id: str
) -> Optional[Dict]:
    """상세 페이지에서 직무 정보 추출"""
    try:
        # ... 기존 코드 (1~11번 항목) ...

        # ============================================
        # 12. 가장 가까운 지하철역 계산 (신규 추가)
        # ============================================
        nearest_station = ""
        station_walk_minutes = None

        if company_address:
            subway = _get_subway_module()
            if subway:
                try:
                    # 주소에서 좌표 파싱
                    coords = subway._parse_location(company_address)
                    
                    if coords:
                        lat, lng = coords
                        # 가장 가까운 역 찾기
                        station_id, walk_minutes = subway._find_nearest_station(lat, lng)
                        
                        if station_id:
                            station_info = subway.stations.get(station_id, {})
                            nearest_station = station_info.get("name", "")
                            station_walk_minutes = walk_minutes
                except Exception as e:
                    if settings.DEBUG:
                        print(f"[Crawler] 지하철역 계산 실패 ({job_id}): {e}")

        # ============================================
        # return문 수정 - 신규 필드 추가
        # ============================================
        return {
            "job_type": normalized or primary_job_type,
            "job_type_raw": ", ".join(job_types[:3]),
            "job_category": category,
            "mvp_category": mvp_category,
            "job_keywords": job_types[:5],
            "industry": "",
            "salary_text": salary_data["text"],
            "salary_min": salary_data["min"],
            "salary_max": salary_data["max"],
            "salary_type": salary_data["type"],
            "company_address": company_address,
            "company_size": company_size,
            "benefits": benefits,
            "job_description": job_description,
            "location_full": company_address,
            "location_sido": location_info.get("sido", ""),
            "location_gugun": location_info.get("gugun", ""),
            "location_dong": location_info.get("dong", ""),
            **deadline_info,
            # ===== 신규 필드 =====
            "nearest_station": nearest_station,
            "station_walk_minutes": station_walk_minutes,
        }

    except Exception as e:
        if settings.DEBUG:
            print(f"[Crawler] 상세 정보 추출 실패 ({job_id}): {e}")
        return None
```

---

## 4. seoul_subway_commute.py 필요 메서드 확인

크롤러에서 사용하는 메서드:

| 메서드 | 용도 | 존재 여부 |
|--------|------|----------|
| `_parse_location(address)` | 주소 → 좌표 변환 | ✅ 확인 필요 |
| `_find_nearest_station(lat, lng)` | 좌표 → 가장 가까운 역 | ✅ 확인 필요 |
| `stations` | 역 정보 딕셔너리 | ✅ 확인 필요 |

### 없으면 추가해야 할 메서드

`seoul_subway_commute.py`에 `_find_nearest_station` 메서드가 없으면 추가:

```python
def _find_nearest_station(self, lat: float, lng: float) -> tuple:
    """
    좌표에서 가장 가까운 지하철역 찾기
    
    Args:
        lat: 위도
        lng: 경도
    
    Returns:
        (station_id, walk_minutes) 또는 (None, None)
    """
    min_distance = float('inf')
    nearest_id = None
    
    for station_id, info in self.stations.items():
        station_lat = info.get("lat")
        station_lng = info.get("lng")
        
        if station_lat is None or station_lng is None:
            continue
        
        # 직선 거리 계산 (Haversine 간소화)
        distance = self._calculate_distance(lat, lng, station_lat, station_lng)
        
        if distance < min_distance:
            min_distance = distance
            nearest_id = station_id
    
    if nearest_id:
        # 거리 → 도보 시간 변환 (분당 80m 기준)
        walk_minutes = int(min_distance / 80) + 1
        return nearest_id, walk_minutes
    
    return None, None

def _calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 간 직선 거리 (미터)"""
    import math
    
    R = 6371000  # 지구 반경 (미터)
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    
    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c
```

---

## 5. 테스트

### 5.1 단위 테스트

```python
# test_nearest_station.py
import asyncio
from app.services.seoul_subway_commute import SeoulSubwayCommute

def test_find_nearest_station():
    subway = SeoulSubwayCommute()
    
    # 강남역 좌표 근처
    lat, lng = 37.498095, 127.027610
    station_id, walk_minutes = subway._find_nearest_station(lat, lng)
    
    print(f"가장 가까운 역: {subway.stations[station_id]['name']}")
    print(f"도보 시간: {walk_minutes}분")
    
    assert station_id is not None
    assert walk_minutes is not None
    assert walk_minutes < 30  # 30분 이내

def test_parse_and_find():
    subway = SeoulSubwayCommute()
    
    address = "서울 강남구 역삼동 823"
    coords = subway._parse_location(address)
    
    if coords:
        lat, lng = coords
        station_id, walk = subway._find_nearest_station(lat, lng)
        print(f"주소: {address}")
        print(f"좌표: {lat}, {lng}")
        print(f"가장 가까운 역: {subway.stations.get(station_id, {}).get('name')}")
        print(f"도보: {walk}분")

if __name__ == "__main__":
    test_find_nearest_station()
    test_parse_and_find()
```

### 5.2 크롤링 테스트

```bash
# 소량 크롤링으로 테스트
cd crawler
python -c "
import asyncio
from app.scrapers import JobKoreaScraper

async def test():
    scraper = JobKoreaScraper(num_workers=1)
    jobs, _ = await scraper.crawl_all_parallel(max_pages=1)
    
    for job in jobs[:3]:
        print(f\"회사: {job.get('company_name')}\")
        print(f\"주소: {job.get('location_full')}\")
        print(f\"가까운 역: {job.get('nearest_station')}\")
        print(f\"도보: {job.get('station_walk_minutes')}분\")
        print('---')
    
    await scraper.close()

asyncio.run(test())
"
```

---

## 6. 작업 순서

```
1. [ ] crawler/app/services/ 디렉토리 생성
2. [ ] seoul_subway_commute.py 복사 (backend → crawler)
3. [ ] __init__.py 생성
4. [ ] _find_nearest_station 메서드 확인/추가
5. [ ] jobkorea.py import 추가
6. [ ] jobkorea.py _fetch_detail_info 수정
7. [ ] 단위 테스트 실행
8. [ ] 소량 크롤링 테스트
9. [ ] 전체 크롤링 실행
```

---

## 7. 주의사항

### 7.1 성능 영향

- `_find_nearest_station`: 역 300개 순회 → ~0.001초
- 공고당 추가 시간: 무시할 수준
- 전체 크롤링에 영향 없음

### 7.2 좌표 파싱 실패 시

- `nearest_station`: 빈 문자열
- `station_walk_minutes`: None
- 검색 시 해당 공고는 통근시간 "계산 불가"로 처리

### 7.3 동기화 주의

`backend/app/services/seoul_subway_commute.py` 수정 시 크롤러 쪽도 동기화 필요.
향후 공통 모듈로 분리 검토.

---

## 8. 예상 결과

### Firestore 저장 데이터 (수정 후)

```json
{
  "id": "jk_12345678",
  "title": "프론트엔드 개발자",
  "company_name": "테크스타트업",
  "location_full": "서울 강남구 역삼동 823",
  "location_gugun": "강남구",
  
  "nearest_station": "역삼역",
  "station_walk_minutes": 5,
  
  "salary_text": "5000~7000만원",
  "salary_min": 5000,
  ...
}
```
