# 통근시간 계산 E2E 테스트 계획

## 1. 테스트 목표

서울 지하철 기반 통근시간 계산 기능(1-9호선 + 신분당선)이 프론트엔드에서 백엔드까지 정상 동작하는지 검증

### 검증 포인트
- [ ] 백엔드 SubwayService 초기화 (328개 역)
- [ ] 통근시간 필터링 정상 작동
- [ ] 프론트엔드 이동시간 표시 (`travel_time_text`)
- [ ] 9호선/신분당선 경로 반영

---

## 2. 테스트 환경 설정

### 2.1 백엔드 서버 시작

```bash
# 터미널 1: 백엔드
cd /Users/stlee/Desktop/jobbot/jobai/backend

# 기존 프로세스 종료
lsof -ti:8000 | xargs kill -9 2>/dev/null

# 가상환경 활성화 & 서버 시작
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**확인 사항**: 서버 로그에서 다음 메시지 확인
```
SubwayService 초기화 완료: 328개 역, 426개 구간
```

### 2.2 프론트엔드 서버 시작

```bash
# 터미널 2: 프론트엔드
cd /Users/stlee/Desktop/jobbot/jobai/frontend
npm run dev
```

**확인 사항**: 포트 번호 확인 (5173, 5174 등)

### 2.3 API 연결 테스트

```bash
# 백엔드 health check
curl http://localhost:8000/health

# 예상 응답: {"status":"ok"}
```

---

## 3. 테스트 시나리오

### 시나리오 1: 기본 통근시간 검색 (2호선)

| 항목 | 값 |
|------|---|
| **검색어** | "건대입구역에서 40분 이내 프론트엔드 개발자" |
| **예상 결과** | 강남, 역삼, 잠실 등 2호선 역 주변 공고 |
| **검증** | `travel_time_text`가 "약 20분", "약 30분" 등으로 표시 |

**프론트엔드 검증 방법**:
1. 검색 입력
2. 결과 카드에서 🚇 아이콘과 이동시간 확인
3. 이동시간 순으로 정렬되어 있는지 확인

### 시나리오 2: 9호선 경로 테스트

| 항목 | 값 |
|------|---|
| **검색어** | "여의도역에서 50분 이내 마케팅" |
| **예상 결과** | 강남, 신논현, 고속터미널 등 9호선 연결 지역 |
| **핵심 검증** | 9호선 직통 경로 (여의도→고속터미널 약 20분) |

### 시나리오 3: 신분당선 경로 테스트

| 항목 | 값 |
|------|---|
| **검색어** | "판교에서 60분 이내 백엔드 개발자" |
| **예상 결과** | 강남, 신사, 양재 등 신분당선 연결 지역 |
| **핵심 검증** | 판교→강남 약 20분으로 계산되어야 함 |

### 시나리오 4: 복합 환승 테스트

| 항목 | 값 |
|------|---|
| **검색어** | "잠실역에서 45분 이내 기획자" |
| **예상 결과** | 2호선 + 환승으로 접근 가능한 지역 |
| **핵심 검증** | 잠실→판교 (2호선→신분당선) 약 30분 |

### 시나리오 5: 좌표 기반 검색 (GPS)

| 항목 | 값 |
|------|---|
| **방법** | 브라우저에서 위치 권한 허용 후 검색 |
| **검색어** | "30분 이내 개발자" |
| **핵심 검증** | 현재 위치 기반으로 통근시간 계산 |

---

## 4. API 직접 테스트 (curl)

### 4.1 기본 검색 테스트

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "건대입구역에서 40분 이내 개발자",
    "page": 1,
    "page_size": 5
  }' | jq '.jobs[] | {title, travel_time_text, location}'
```

**예상 응답**:
```json
{
  "title": "프론트엔드 개발자",
  "travel_time_text": "약 20분",
  "location": "서울 강남구"
}
```

### 4.2 9호선 경로 테스트

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "여의도역에서 30분 이내 마케터",
    "page": 1,
    "page_size": 5
  }' | jq '.jobs[] | {title, travel_time_text}'
```

### 4.3 신분당선 테스트

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "판교역에서 40분 이내 개발자 연봉 5000만원 이상",
    "page": 1,
    "page_size": 5
  }' | jq '.jobs[] | {title, travel_time_text, salary}'
```

### 4.4 좌표 기반 테스트 (건대입구역 좌표)

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "30분 이내 프론트엔드",
    "user_lat": 37.5403,
    "user_lng": 127.0694,
    "page": 1,
    "page_size": 5
  }' | jq '.jobs[] | {title, travel_time_text}'
```

---

## 5. 프론트엔드 UI 검증 체크리스트

### 5.1 JobCard 컴포넌트

| 항목 | 확인 |
|------|------|
| 🚇 이모지 표시 | [ ] |
| `travel_time_text` 표시 (예: "약 30분") | [ ] |
| 파란색 배지 스타일 | [ ] |
| 이동시간 없는 공고: "이동시간 정보 없음" | [ ] |

### 5.2 검색 결과

| 항목 | 확인 |
|------|------|
| 이동시간순 정렬 | [ ] |
| 최대 시간 초과 공고 제외 | [ ] |
| 페이지네이션 동작 | [ ] |

---

## 6. 자동화 테스트 스크립트

### 6.1 백엔드 통합 테스트

```python
# tests/test_e2e_commute.py

import asyncio
import httpx

BASE_URL = "http://localhost:8000"

async def test_commute_search():
    """통근시간 검색 E2E 테스트"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 테스트 케이스들
        test_cases = [
            {
                "name": "건대입구 40분 이내",
                "message": "건대입구역에서 40분 이내 개발자",
                "expect_travel_time": True,
            },
            {
                "name": "여의도 30분 이내 (9호선)",
                "message": "여의도역에서 30분 이내 마케팅",
                "expect_travel_time": True,
            },
            {
                "name": "판교 40분 이내 (신분당선)",
                "message": "판교역에서 40분 이내 백엔드",
                "expect_travel_time": True,
            },
        ]

        for case in test_cases:
            print(f"\n=== {case['name']} ===")

            response = await client.post(
                f"{BASE_URL}/chat",
                json={
                    "message": case["message"],
                    "page": 1,
                    "page_size": 5
                }
            )

            assert response.status_code == 200, f"Status: {response.status_code}"

            data = response.json()
            jobs = data.get("jobs", [])

            print(f"결과 수: {len(jobs)}건")

            if case["expect_travel_time"] and jobs:
                for job in jobs[:3]:
                    travel_time = job.get("travel_time_text", "없음")
                    print(f"  - {job['title'][:30]}: {travel_time}")

                    # travel_time_text가 있어야 함
                    assert job.get("travel_time_text"), "travel_time_text 없음"
                    assert job.get("travel_time_minutes"), "travel_time_minutes 없음"

            print("✅ PASS")

if __name__ == "__main__":
    asyncio.run(test_commute_search())
```

### 6.2 실행 방법

```bash
# 백엔드 서버가 실행 중인 상태에서
cd /Users/stlee/Desktop/jobbot/jobai
python tests/test_e2e_commute.py
```

---

## 7. 수동 테스트 절차

### Step 1: 환경 확인

```bash
# 1. 백엔드 서버 상태
curl http://localhost:8000/health

# 2. SubwayService 상태 (로그 확인)
# "SubwayService 초기화 완료: 328개 역" 메시지 확인
```

### Step 2: 브라우저에서 테스트

1. **브라우저 열기**: `http://localhost:5173` (또는 Vite가 표시한 포트)

2. **검색어 입력**:
   ```
   건대입구역에서 30분 이내 프론트엔드 개발자 연봉 5000 이상
   ```

3. **결과 확인**:
   - 각 공고 카드에 🚇 이동시간 표시 확인
   - "약 20분", "약 30분" 형식 확인
   - 30분 초과 공고가 없는지 확인

4. **9호선 테스트**:
   ```
   여의도역에서 40분 이내 마케터
   ```

5. **신분당선 테스트**:
   ```
   판교역에서 50분 이내 개발자
   ```

### Step 3: 콘솔 로그 확인

브라우저 개발자 도구(F12) → Network 탭에서:
- `/chat` 요청의 Response 확인
- `jobs` 배열 내 `travel_time_minutes`, `travel_time_text` 필드 확인

---

## 8. 예상 통근시간 기준값

| 출발역 | 도착역 | 예상 시간 | 비고 |
|--------|--------|----------|------|
| 건대입구역 | 강남역 | 약 30분 | 2호선 직통 |
| 건대입구역 | 잠실역 | 약 20분 | 2호선 직통 |
| 건대입구역 | 여의도역 | 약 40분 | 환승 필요 |
| 여의도역 | 고속터미널역 | 약 30분 | 9호선 직통 |
| 여의도역 | 신논현역 | 약 30분 | 9호선 직통 |
| 강남역 | 판교역 | 약 20분 | 신분당선 직통 |
| 잠실역 | 판교역 | 약 30분 | 2호선→신분당선 |
| 홍대입구역 | 판교역 | 약 50분 | 2호선→신분당선 |

---

## 9. 문제 발생 시 디버깅

### 9.1 통근시간이 표시되지 않는 경우

```bash
# 백엔드 로그 확인
# Stage 3 로그 확인: "Stage 3: 지하철 기반 거리 필터 사용"

# SubwayService 상태 확인
curl http://localhost:8000/health
```

### 9.2 통근시간이 이상하게 계산되는 경우

```bash
# 직접 통근시간 계산 테스트
cd /Users/stlee/Desktop/jobbot/jobai/backend
python3 -c "
from app.services.seoul_subway_commute import SeoulSubwayCommute
c = SeoulSubwayCommute()
print(c.calculate('건대입구역', '강남역'))
print(c.calculate('여의도역', '고속터미널역'))
print(c.calculate('강남역', '판교역'))
"
```

### 9.3 CORS 에러 발생 시

```bash
# backend/.env 파일 확인
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:5174,...

# 백엔드 재시작
lsof -ti:8000 | xargs kill -9
uvicorn app.main:app --reload --port 8000
```

---

## 10. 테스트 완료 체크리스트

### 필수 항목

- [ ] 백엔드 SubwayService 328개 역 로드 확인
- [ ] 기본 검색 (2호선) - 이동시간 표시 확인
- [ ] 9호선 경로 - 여의도 출발 테스트
- [ ] 신분당선 경로 - 판교 출발 테스트
- [ ] 환승 경로 - 잠실→판교 테스트
- [ ] 프론트엔드 UI - 🚇 이동시간 배지 표시

### 선택 항목

- [ ] GPS 좌표 기반 검색
- [ ] 페이지네이션 동작
- [ ] 더 보기 기능
- [ ] 에러 핸들링

---

## 11. 테스트 실행 요약

```bash
# 1. 백엔드 시작
cd backend && source venv/bin/activate && uvicorn app.main:app --reload

# 2. 프론트엔드 시작 (새 터미널)
cd frontend && npm run dev

# 3. API 테스트
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "건대입구역에서 30분 이내 개발자", "page": 1, "page_size": 3}' \
  | jq '.jobs[] | {title, travel_time_text}'

# 4. 브라우저 테스트
# http://localhost:5173 접속 후 검색
```
