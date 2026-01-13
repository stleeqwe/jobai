# JobChat 아키텍처 V5: Hybrid Search System

## 개요

Function Calling + 하드코딩 규칙 기반의 V4 아키텍처를 폐기하고,
DB 필터 + 벡터 검색 + AI 평가를 조합한 Hybrid 아키텍처로 전환한다.

### 배경

**V4의 한계**
- "강남역 근처"를 통근시간으로 해석 → 사용자 의도와 불일치
- 위치/직무 조건을 하드코딩 규칙으로 처리 → 유연성 부족
- Function Calling 스키마 관리 복잡

**V5 목표**
- 구조화된 조건은 DB에서 정확히 필터링
- 의미적 조건은 벡터 검색으로 처리
- 자연어 뉘앙스는 AI가 직접 판단

---

## 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Query                                │
│              "강남역 근처 앱 개발자 연봉 4천만원 이상"              │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Query Understanding                           │
│                      (Gemini 2.5 Flash)                         │
│                                                                  │
│  Input: 사용자 자연어 쿼리                                        │
│  Output:                                                         │
│    - hard_filters: {salary_min: 4000, location_city: "서울"}     │
│    - semantic_query: "앱 개발자"                                  │
│    - context_conditions: ["강남역 근처"]                          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Stage 1: DB Filter (Hard Constraints)            │
│                          Firestore                               │
│                                                                  │
│  - salary_min >= 4000                                            │
│  - location_city == "서울"                                       │
│  - is_active == true                                             │
│                                                                  │
│  74,000건 → ~15,000건                                            │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              Stage 2: Vector Search (Semantic Match)             │
│                    Vector DB (Firestore / Vertex AI)             │
│                                                                  │
│  Query Embedding: "앱 개발자" → [0.12, -0.34, 0.56, ...]         │
│  Similarity Search: cosine similarity                            │
│  Top-K: 200                                                      │
│                                                                  │
│  15,000건 → 200건                                                 │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│               Stage 3: AI Evaluation (Nuanced Judge)             │
│                      (Gemini 2.5 Flash)                          │
│                                                                  │
│  Input:                                                          │
│    - 200개 후보 공고 (제목, 회사, 주소, 연봉, 설명)                 │
│    - context_conditions: ["강남역 근처"]                          │
│    - 사용자 원본 쿼리                                             │
│                                                                  │
│  AI 판단:                                                        │
│    - "강남역 근처" = 강남역 반경 ~3km 이내                         │
│    - 주소 "서울 강남구 역삼동" → 강남역 근처 ✓                     │
│    - 주소 "서울 금천구 가산동" → 강남역 근처 ✗                     │
│                                                                  │
│  200건 → 최종 결과 (~20건)                                        │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Response Generation                         │
│                      (Gemini 2.5 Flash)                          │
│                                                                  │
│  - 결과 요약                                                      │
│  - 자연스러운 응답 생성                                           │
│  - 추가 질문 유도                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 데이터 모델

### Firestore: jobs 컬렉션

```javascript
{
  // 기본 정보
  id: "jk_48123456",
  title: "Flutter 앱 개발자",
  company_name: "스타트업A",
  url: "https://jobkorea.co.kr/...",

  // 구조화된 필터용 (Stage 1)
  salary_min: 4000,           // 숫자, 인덱싱
  salary_max: 6000,
  location_city: "서울",       // 인덱싱
  location_district: "강남구", // 인덱싱
  is_active: true,            // 인덱싱

  // 원본 텍스트 (AI 평가용)
  location_full: "서울 강남구 역삼동 123-45",
  salary_text: "연봉 4,000~6,000만원",
  description: "...",

  // 벡터 임베딩 (Stage 2)
  title_embedding: [0.12, -0.34, ...],  // 768 or 1536 dimensions

  // 메타데이터
  created_at: Timestamp,
  updated_at: Timestamp,
  crawled_at: Timestamp
}
```

### 인덱스 설계

```
# Firestore Composite Index
Collection: jobs
Fields:
  - is_active (ASC)
  - location_city (ASC)
  - salary_min (ASC)
```

---

## 컴포넌트 상세

### 1. Query Understanding

사용자 쿼리를 분석하여 3가지 카테고리로 분류한다.

```python
# Input
query = "강남역 근처 앱 개발자 연봉 4천만원 이상"

# Output
{
  "hard_filters": {
    "salary_min": 4000,
    "location_city": "서울"
  },
  "semantic_query": "앱 개발자",
  "context_conditions": [
    {
      "type": "location_proximity",
      "reference": "강남역",
      "description": "강남역 근처"
    }
  ]
}
```

**분류 기준**

| 카테고리 | 설명 | 예시 |
|----------|------|------|
| hard_filters | 수치/정확 비교 가능 | 연봉 >= 4000, 서울 지역 |
| semantic_query | 의미적 매칭 필요 | 앱 개발자, 프론트엔드 |
| context_conditions | AI 판단 필요 | 강남역 근처, 야근 없는 |

### 2. Vector Search

**임베딩 모델 옵션**

| 모델 | 차원 | 특징 |
|------|------|------|
| Vertex AI text-embedding | 768 | GCP 네이티브 |
| OpenAI text-embedding-3 | 1536 | 고성능 |
| Gemini Embedding | 768 | Gemini 생태계 |

**임베딩 대상**
- `title` + `description` 조합
- 또는 `title`만 (비용 절감)

**벡터 DB 옵션**

| 옵션 | 장점 | 단점 |
|------|------|------|
| Firestore Vector Search | 기존 인프라 | 기능 제한적 |
| Vertex AI Vector Search | 대규모, 고성능 | 추가 비용 |
| Pinecone | 전문 벡터 DB | 외부 서비스 |

**권장: Vertex AI Vector Search**
- GCP 생태계 통합
- 74K 규모에 적합
- 관리형 서비스

### 3. AI Evaluation

200개 후보를 AI가 직접 평가하여 최종 결과 선별.

**프롬프트 구조**

```
시스템:
당신은 채용공고 검색 전문가입니다.
사용자의 요구사항과 후보 공고들을 비교하여 가장 적합한 공고를 선별하세요.

사용자 요구사항:
- 원본 쿼리: "강남역 근처 앱 개발자 연봉 4천만원 이상"
- 위치 조건: "강남역 근처" (강남역 반경 약 3km 이내로 해석)

후보 공고 목록:
1. [제목] Flutter 앱 개발자
   [회사] 스타트업A
   [주소] 서울 강남구 역삼동 123-45
   [연봉] 4,000~6,000만원
   ...

평가 기준:
1. 위치가 "강남역 근처" 조건에 부합하는가?
2. 직무가 사용자가 원하는 "앱 개발자"에 해당하는가?
3. 기타 조건들을 충족하는가?

JSON 형식으로 적합한 공고 ID 목록을 반환하세요.
```

---

## 비용 분석

### 검색당 비용 (74,000건 기준)

| 단계 | 처리량 | 비용 |
|------|--------|------|
| Query Understanding | 1회 AI 호출 | ~5원 |
| DB Filter | Firestore 읽기 | ~1원 |
| Vector Search | 유사도 검색 | ~2원 |
| AI Evaluation | 200개 평가 | ~25원 |
| Response Generation | 1회 AI 호출 | ~5원 |
| **합계** | | **~38원/검색** |

### 월간 비용 예상

| 일 검색량 | 월 비용 |
|----------|---------|
| 100회 | ~11만원 |
| 1,000회 | ~110만원 |
| 10,000회 | ~1,100만원 |

### 임베딩 비용 (1회성)

- 74,000건 × ~200 토큰 = 14.8M 토큰
- Vertex AI Embedding: ~$0.025/1K tokens
- **총 ~$370 (약 50만원) - 1회성**

---

## 크롤링 파이프라인 변경

### 현재 (V4)

```
크롤링 → 정규화 → Firestore 저장
```

### 변경 (V5)

```
크롤링 → 정규화 → 임베딩 생성 → Firestore 저장
                      │
                      ▼
              Vertex AI Vector Search 인덱스 동기화
```

### 크롤러 수정 사항

```python
# 크롤링 시 임베딩 생성
async def process_job(job: dict) -> dict:
    # 기존 정규화
    normalized = normalize_job(job)

    # 임베딩 생성
    text_for_embedding = f"{job['title']} {job['description'][:500]}"
    embedding = await generate_embedding(text_for_embedding)

    normalized['title_embedding'] = embedding
    return normalized
```

---

## 구현 로드맵

### Phase 1: 인프라 준비
- [ ] Vertex AI Vector Search 설정
- [ ] Firestore 인덱스 추가 (salary_min, location_city)
- [ ] 임베딩 모델 선정 및 테스트

### Phase 2: 데이터 마이그레이션
- [ ] 기존 74K 공고 임베딩 생성 (배치)
- [ ] Firestore 필드 추가 (title_embedding)
- [ ] Vector Search 인덱스 구축

### Phase 3: 백엔드 구현
- [ ] Query Understanding 모듈
- [ ] Vector Search 클라이언트
- [ ] AI Evaluation 파이프라인
- [ ] 기존 gemini.py 대체

### Phase 4: 크롤러 연동
- [ ] 신규 공고 임베딩 자동 생성
- [ ] Vector Search 인덱스 실시간 동기화

### Phase 5: 테스트 및 전환
- [ ] A/B 테스트 (V4 vs V5)
- [ ] 성능 모니터링
- [ ] V4 코드 제거

---

## 기존 코드 영향 범위

### 삭제 대상
- `app/services/gemini.py` - 3-Stage 파이프라인
- `app/services/seoul_subway_commute.py` - 지하철 통근시간 계산
- `app/services/subway.py` - 지하철 서비스 래퍼
- `app/services/location.py` - 위치 파싱

### 신규 생성
- `app/services/query_understanding.py` - 쿼리 분석
- `app/services/vector_search.py` - 벡터 검색
- `app/services/ai_evaluator.py` - AI 평가
- `app/services/search_pipeline.py` - 통합 파이프라인

### 수정 대상
- `crawler/app/scrapers/jobkorea.py` - 임베딩 생성 추가
- `app/main.py` - 엔드포인트 연결

---

## 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| Vector Search 지연 | 검색 속도 저하 | 캐싱, 인덱스 최적화 |
| 임베딩 비용 증가 | 크롤링 비용 상승 | title만 임베딩 |
| AI 평가 품질 | 부정확한 결과 | 프롬프트 튜닝, Few-shot |
| Vertex AI 장애 | 서비스 중단 | Fallback to DB only |

---

## 부록: V4 vs V5 비교

| 항목 | V4 (현재) | V5 (Hybrid) |
|------|----------|-------------|
| 쿼리 분석 | Function Calling | LLM 자유 추론 |
| 연봉 필터 | 하드코딩 규칙 | DB 필터 |
| 직무 매칭 | AI 의미 분석 | 벡터 검색 |
| 위치 판단 | 지하철 통근시간 | AI 직접 판단 |
| 복잡도 | 높음 | 중간 |
| 유연성 | 낮음 | 높음 |
| 확장성 | 800건 한계 | 10만건+ 가능 |
