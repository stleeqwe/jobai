# JobChat 변경 이력

## 현재 버전: V6 (Simple Agentic)

**Last Updated:** 2026-01-14

---

## V6 - Simple Agentic (2026-01-14)

### 핵심 변경

| 항목 | 변경 내용 |
|------|----------|
| **아키텍처** | LLM을 자율적 판단자로 활용 (파라미터 추출기 X) |
| **AI 모델** | Gemini 3 Flash + Thinking Mode (`thinking_budget=8192`) |
| **통근시간** | 지하철 모듈 기반 (비용 $0) |
| **검색 흐름** | LLM 자율 판단 → 정보 부족 시 질문 / 충분 시 search_jobs 호출 |

### 주요 파일

```
backend/app/services/
├── gemini.py              # Simple Agentic LLM 서비스
├── job_search.py          # DB 검색 + 통근시간 계산
├── subway.py              # 지하철 서비스 래퍼
└── seoul_subway_commute.py # 지하철 통근시간 핵심 모듈
```

### API

```
POST /chat          - 자연어 검색 (LLM 자율 판단)
POST /chat/more     - 더보기 (LLM 호출 없음, 캐시 기반)
GET  /model-info    - AI 모델 정보 확인
GET  /health        - 서비스 상태 확인
```

---

## V5 - Hybrid Search (미구현)

> 설계만 진행, V6으로 대체됨

### 계획했던 내용
- Vector Search (Vertex AI) 기반 의미 검색
- DB 필터 + 벡터 검색 + AI 평가 3단계
- 임베딩 비용 문제로 미구현

---

## V4 - 지하철 기반 통근시간 (2026-01-13)

### 핵심 변경

| 항목 | 변경 내용 |
|------|----------|
| **통근시간** | Google Maps API → 지하철 모듈로 대체 |
| **비용 절감** | 검색당 $1.25 → $0 |
| **지원 노선** | 1-9호선 + 신분당선 (328개 역) |

### 지하철 모듈 특징
- 순수 Python, 외부 API 없음
- Dijkstra 알고리즘 최단경로
- 10분 단위 반올림 (±10분 정확도)
- 환승 시간 반영 (3-7분)

---

## V3 - 3-Stage Sequential Filter (2026-01-13)

### 아키텍처

```
사용자 입력 → Phase 0 (필수 정보 수집)
           → Stage 1 (AI 직무 필터)
           → Stage 2 (연봉 필터)
           → Stage 3 (Maps API 거리 필터)
           → 결과
```

### 한계
- Google Maps API 비용 ($1.25/검색)
- 복잡한 파이프라인
- Function Calling 강제로 유연성 부족

---

## V2 - 2-Stage Hybrid (2026-01-12)

### 시도한 내용
- AI 직무 필터 + DB 연봉 필터

### 문제점
- 위치 필터 실패 ("을지로역" → "중구" 매핑 불가)
- 직무 매칭 부정확
- 대부분 공고가 `salary_min=None`

---

## V1 - MVP (2026-01-10)

### 초기 기능
- 자연어 검색 기본 기능
- 잡코리아 크롤러
- Firestore 저장
- React 프론트엔드

---

## 크롤러 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2026-01-14 | `nearest_station` 필드 추가 |
| 2026-01-13 | `location_full` 필드 누락 수정 |
| 2026-01-12 | HTML 셀렉터 수정 (`li.devloopArea`) |
| 2026-01-12 | MVP 필터링 개선 |
| 2026-01-10 | 잡코리아 크롤러 초기 구현 |

---

## 기술 스택 변경

| 버전 | AI 모델 | 통근시간 | SDK |
|------|--------|---------|-----|
| V6 | Gemini 3 Flash | 지하철 모듈 | google.genai |
| V4 | Gemini 2.0 Flash | 지하철 모듈 | google.generativeai |
| V3 | Gemini 2.0 Flash | Google Maps | google.generativeai |
| V1-V2 | Gemini 2.0 Flash-Lite | - | google.generativeai |

---

## 삭제된 파일

### V6 정리 (2026-01-14)

| 파일 | 이유 |
|------|------|
| `gemini_v4_backup.py` | V4 백업, V6 완료 후 불필요 |
| `job_search_v4_backup.py` | V4 백업, V6 완료 후 불필요 |
| `maps.py` | Google Maps API, 지하철 모듈로 대체 |
| `location.py` | 위치 파싱, 지하철 모듈에 통합 |

### 삭제된 문서

| 문서 | 이유 |
|------|------|
| `ARCHITECTURE_V3.md` | V3 아키텍처, V6으로 대체 |
| `ARCHITECTURE_V5_HYBRID.md` | V5 설계, 미구현 |
| `JOBCHAT_V6_MIGRATION_PLAN.md` | 마이그레이션 완료 |
