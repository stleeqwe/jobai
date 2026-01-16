# 데이터베이스 검색 검증 테스트 계획

**작성일**: 2026-01-16
**목적**: 크롤러로 수집한 데이터베이스가 실제 검색 API에서 정상적으로 반환되는지 검증

---

## 1. 테스트 범위

### 검증 대상
| 계층 | 검증 항목 |
|------|-----------|
| **DB 직접 조회** | Firestore에서 데이터가 올바르게 조회되는지 |
| **검색 서비스** | `job_search.py`의 필터링 로직이 정상 동작하는지 |
| **API 엔드포인트** | `/chat` API가 실제 DB 데이터를 반환하는지 |
| **데이터 무결성** | 검색 결과가 DB 원본과 일치하는지 |

### 테스트 순서
```
1. DB 직접 검증 (Firestore)
   ↓
2. 검색 서비스 단위 검증 (job_search.py)
   ↓
3. API 통합 검증 (/chat)
   ↓
4. 데이터 무결성 검증 (DB ↔ API 일치)
```

---

## 2. TC-100: DB 직접 조회 검증

### TC-101: 활성 공고 존재 확인
**목적**: `is_active=True`인 공고가 DB에 존재하는지 확인

```python
# 검증 쿼리
db.collection("jobs").where("is_active", "==", True).limit(10).stream()
```

**합격 기준**:
- [ ] 활성 공고 1건 이상 존재
- [ ] 각 공고에 필수 필드 존재 (`title`, `company_name`, `url`)

### TC-102: 필드 완성도 검증
**목적**: 검색에 필요한 필드가 채워져 있는지 확인

| 필드 | 필수 여부 | 설명 |
|------|-----------|------|
| `title` | 필수 | 공고 제목 (키워드 매칭) |
| `company_name` | 필수 | 회사명 |
| `job_type_raw` | 권장 | 직무 유형 (키워드 매칭) |
| `job_keywords` | 권장 | 키워드 배열 |
| `salary_min` | 권장 | 최소 연봉 (연봉 필터) |
| `location_full` | 권장 | 상세 위치 |
| `is_active` | 필수 | 활성 상태 |

**합격 기준**:
- [ ] `title` 빈 값 비율 < 1%
- [ ] `company_name` 빈 값 비율 < 1%
- [ ] `salary_min` 존재 비율 > 50%

### TC-103: 샘플 데이터 조회
**목적**: 무작위 샘플 공고 ID로 DB 조회 가능 확인

```python
# 검증 방법
1. DB에서 무작위 10개 공고 ID 추출
2. 각 ID로 직접 조회
3. 조회 결과 일치 확인
```

**합격 기준**:
- [ ] 10개 모두 조회 성공 (100%)

---

## 3. TC-200: 검색 서비스 검증

### TC-201: 키워드 검색 반환
**목적**: `search_jobs_with_commute()`가 키워드로 결과 반환

```python
# 테스트 케이스
test_keywords = [
    ["마케팅"],
    ["개발", "백엔드"],
    ["디자인", "UI"],
    ["영업"],
    ["경영지원"],
]
```

**검증**:
```python
for keywords in test_keywords:
    result = await search_jobs_with_commute(job_keywords=keywords)
    assert result["total_count"] > 0, f"키워드 {keywords}에 결과 없음"
```

**합격 기준**:
- [ ] 각 키워드별 1건 이상 결과
- [ ] 결과의 `title` 또는 `job_type_raw`에 키워드 포함

### TC-202: 연봉 필터 동작
**목적**: 연봉 조건이 올바르게 필터링되는지 확인

```python
# 테스트 케이스
result_3000 = await search_jobs_with_commute(
    job_keywords=["마케팅"],
    salary_min=3000
)
result_5000 = await search_jobs_with_commute(
    job_keywords=["마케팅"],
    salary_min=5000
)

# 검증
assert result_3000["total_count"] >= result_5000["total_count"]
```

**합격 기준**:
- [ ] 높은 연봉 조건 → 적은 결과 (논리적 일관성)
- [ ] 반환된 공고의 `salary_min` >= 지정 연봉

### TC-203: 회사 위치 필터
**목적**: `company_location` 필터가 동작하는지 확인

```python
# 테스트 케이스
result = await search_jobs_with_commute(
    job_keywords=["마케팅"],
    company_location="강남"
)

# 검증: location_full에 "강남" 포함
for job in result["jobs"]:
    assert "강남" in job.get("location_full", "")
```

**합격 기준**:
- [ ] 모든 결과의 위치에 필터 문자열 포함

### TC-204: 결과 제한 (limit)
**목적**: 과도한 결과 반환 방지

```python
# 기본 limit = 2000
result = await search_jobs_with_commute(job_keywords=["개발"])
assert result["total_count"] <= 2000
```

**합격 기준**:
- [ ] 결과 수 <= 설정된 limit

---

## 4. TC-300: API 통합 검증

### TC-301: /chat API 검색 결과 반환
**목적**: 자연어 쿼리로 실제 DB 데이터가 반환되는지 확인

```python
# 테스트 케이스
test_queries = [
    "마케팅 일자리 찾아줘",
    "백엔드 개발자 채용 공고",
    "디자이너 공고 보여줘",
    "영업 직무 알려줘",
]

for query in test_queries:
    response = await client.post("/chat", json={"message": query})
    result = response.json()
    assert result["success"] == True
    assert len(result["jobs"]) > 0, f"쿼리 '{query}'에 결과 없음"
```

**합격 기준**:
- [ ] 모든 테스트 쿼리에서 1건 이상 반환
- [ ] `success: true` 응답

### TC-302: 반환 데이터 필드 완성도
**목적**: API 응답의 필드가 올바르게 채워졌는지 확인

```python
# 검증 필드
required_fields = ["id", "company_name", "title", "url"]
recommended_fields = ["location", "salary", "deadline"]

for job in result["jobs"]:
    for field in required_fields:
        assert job.get(field), f"필수 필드 {field} 누락"
```

**합격 기준**:
- [ ] 필수 필드 100% 존재
- [ ] 권장 필드 80% 이상 존재

### TC-303: 검색 파라미터 파싱 검증
**목적**: Gemini가 쿼리를 올바르게 파싱하는지 확인

```python
# 테스트 케이스
query = "연봉 4000 이상 마케팅 직무"
response = await client.post("/chat", json={"message": query})
result = response.json()

search_params = result["search_params"]
assert "마케팅" in search_params.get("job_keywords", [])
assert search_params.get("salary_min") >= 4000
```

**합격 기준**:
- [ ] 키워드 정확히 추출
- [ ] 연봉 조건 정확히 추출

### TC-304: 연속 대화 결과 일관성
**목적**: 동일 대화에서 필터 추가 시 결과 범위 축소

```python
# Step 1: 넓은 검색
resp1 = await chat("마케팅 일자리")
conv_id = resp1["conversation_id"]

# Step 2: 필터 추가
resp2 = await chat("연봉 5000 이상으로", conv_id)

# 검증: 결과 범위 축소
assert resp2["jobs_count"] <= resp1["jobs_count"]
```

**합격 기준**:
- [ ] 필터 추가 시 결과 수 감소 또는 유지

---

## 5. TC-400: 데이터 무결성 검증

### TC-401: API 결과 ↔ DB 일치
**목적**: API가 반환한 공고가 실제 DB에 존재하는지 확인

```python
# 검증 방법
1. /chat API로 검색 결과 획득
2. 결과의 job ID로 DB 직접 조회
3. 필드 값 일치 확인
```

```python
# 구현
for job in api_result["jobs"]:
    job_id = job["id"]  # jk_12345678

    # DB 직접 조회
    db_doc = db.collection("jobs").document(job_id).get()
    assert db_doc.exists, f"API 결과 {job_id}가 DB에 없음"

    db_job = db_doc.to_dict()
    assert job["title"] == db_job["title"]
    assert job["company_name"] == db_job["company_name"]
```

**합격 기준**:
- [ ] API 결과 100% DB에 존재
- [ ] 핵심 필드 값 100% 일치

### TC-402: 수집 ID 검색 가능 검증
**목적**: 크롤러가 수집한 ID가 검색 가능한지 확인

```python
# 검증 방법
1. DB에서 최근 수집된 공고 100개 샘플링
2. 각 공고의 title 키워드로 검색
3. 해당 공고가 결과에 포함되는지 확인
```

```python
# 구현
sample_jobs = db.collection("jobs") \
    .where("is_active", "==", True) \
    .order_by("crawled_at", direction="DESCENDING") \
    .limit(100).stream()

found_count = 0
for doc in sample_jobs:
    job = doc.to_dict()
    keyword = job["title"].split()[0]  # 첫 단어

    # 검색
    result = await search_jobs_with_commute(job_keywords=[keyword])

    # 해당 공고 존재 확인
    job_ids = [j["id"] for j in result["jobs"]]
    if doc.id in job_ids:
        found_count += 1

assert found_count / 100 >= 0.8, f"검색 가능 비율: {found_count}%"
```

**합격 기준**:
- [ ] 샘플 공고의 80% 이상 검색 가능

### TC-403: 비활성 공고 제외 확인
**목적**: `is_active=False` 공고가 검색에서 제외되는지 확인

```python
# 검증 방법
1. DB에서 is_active=False인 공고 추출
2. 해당 공고 ID가 검색 결과에 없는지 확인
```

**합격 기준**:
- [ ] 비활성 공고 0건 반환

---

## 6. 테스트 실행 계획

### 실행 스크립트
```bash
# tests/e2e/test_db_search_verification.py
cd backend && source venv/bin/activate
python -m pytest tests/e2e/test_db_search_verification.py -v
```

### 환경 요구사항
- [ ] 백엔드 서버 실행 (`uvicorn app.main:app --port 8000`)
- [ ] Firestore 연결 (`GOOGLE_APPLICATION_CREDENTIALS` 설정)
- [ ] Gemini API 키 설정 (`GEMINI_API_KEY`)

### 테스트 구조
```
tests/
└── e2e/
    ├── conftest.py                      # pytest fixtures
    ├── test_db_direct.py                # TC-100: DB 직접 검증
    ├── test_search_service.py           # TC-200: 검색 서비스 검증
    ├── test_api_integration.py          # TC-300: API 통합 검증
    └── test_data_integrity.py           # TC-400: 데이터 무결성 검증
```

---

## 7. 합격 기준 요약

| 테스트 그룹 | 항목 수 | 합격 기준 |
|-------------|---------|-----------|
| TC-100: DB 직접 | 3 | 100% |
| TC-200: 검색 서비스 | 4 | 100% |
| TC-300: API 통합 | 4 | 75% (3/4) |
| TC-400: 데이터 무결성 | 3 | 100% |

**전체 합격 기준**: TC-100, TC-200, TC-400 100% + TC-300 75%

---

## 8. 예상 이슈 및 대응

| 이슈 | 원인 | 대응 |
|------|------|------|
| 검색 결과 0건 | 키워드 불일치 | `job_keywords` 배열 확인 |
| DB 조회 실패 | 인증 미설정 | `GOOGLE_APPLICATION_CREDENTIALS` 확인 |
| API 타임아웃 | Gemini 응답 지연 | timeout 증가 (60초) |
| 필드 불일치 | 스키마 변경 | 크롤러 ↔ 백엔드 스키마 동기화 |

---

## 9. 실행 명령어

```bash
# 전체 테스트
python tests/scripts/run_db_search_tests.py

# 개별 테스트
python tests/scripts/run_db_search_tests.py --tc 100  # DB 직접
python tests/scripts/run_db_search_tests.py --tc 200  # 검색 서비스
python tests/scripts/run_db_search_tests.py --tc 300  # API 통합
python tests/scripts/run_db_search_tests.py --tc 400  # 무결성
```
