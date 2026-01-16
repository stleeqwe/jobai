# JobKorea 크롤러 유지보수 가이드

## 개요

잡코리아에서 채용공고를 수집하여 Firestore에 저장하는 크롤러입니다.

## 주요 이슈 및 해결 기록

### 2026-01-13: location_full 필드 누락 문제

**문제 상황**
- 780개 공고 중 653개에서 `location_full` 필드가 비어있음
- 위치 기반 필터링(지하철 통근시간 계산)이 작동하지 않음

**원인 분석**
- `_fetch_detail_info()`에서 `company_address`로 주소를 추출했으나
- 반환 딕셔너리에 `location_full` 키를 포함하지 않아 Firestore에 저장되지 않음

**데이터 출처별 현황**
| 출처 | 필드 | 예시 | 비고 |
|------|------|------|------|
| 목록 페이지 태그 | `location_full` | "서울 강남구" | 구/군 수준만 제공 |
| 상세 페이지 | `company_address` | "서울 강남구 테헤란로 123" | 상세 주소 포함 |
| JSON-LD | `addressLocality` | "서울특별시 강남구" | 가장 정확 |

**수정 내용**
```python
# jobkorea.py - _fetch_detail_info()

# 1. JSON-LD addressLocality 파싱 추가
json_ld_match = re.search(r'"addressLocality"\s*:\s*"([^"]+)"', html)
if json_ld_match:
    company_address = json_ld_match.group(1).strip()

# 2. 반환값에 location_full 포함
return {
    ...
    "location_full": company_address,  # 추가됨
    "company_address": company_address,
    ...
}
```

**데이터 마이그레이션**
- 기존 데이터는 `scripts/update_location_full.py` 스크립트로 일괄 업데이트
- `company_address` → `location_full` 복사

---

## 데이터 구조

### Firestore 필드 (jobs 컬렉션)

| 필드 | 타입 | 설명 | 필수 |
|------|------|------|------|
| `id` | string | 공고 고유 ID (jk_12345678) | O |
| `title` | string | 공고 제목 | O |
| `company_name` | string | 회사명 | O |
| `location_full` | string | 전체 주소 (거리 계산용) | O |
| `location_sido` | string | 시/도 | |
| `location_gugun` | string | 구/군 | |
| `location_dong` | string | 동 | |
| `company_address` | string | 회사 주소 (원본) | |
| `salary_text` | string | 연봉 텍스트 | |
| `salary_min` | number | 최소 연봉 (만원) | |
| `salary_max` | number | 최대 연봉 (만원) | |
| `job_type` | string | 고용 형태 | |
| `experience` | string | 경력 요건 | |
| `education` | string | 학력 요건 | |
| `description` | string | 상세 설명 | |
| `url` | string | 공고 URL | O |
| `created_at` | timestamp | 수집 시간 | O |
| `deadline` | string | 마감일 | |

### 위치 데이터 우선순위

1. **JSON-LD `addressLocality`** - 가장 정확, 우선 사용
2. **상세 페이지 주소 파싱** - fallback
3. **목록 페이지 태그** - 구/군 수준만 제공

---

## 크롤링 흐름

```
1. 목록 페이지 수집 (AjaxClient)
   └─ AJAX 엔드포인트로 Job ID 수집

2. 상세 페이지 수집 (DetailCrawlOrchestrator)
   ├─ 병렬 워커로 상세 페이지 fetch
   └─ DetailPageParser로 파싱
       ├─ JSON-LD 파싱 (title, company, address)
       ├─ CSS 셀렉터 폴백
       └─ 정규식 패턴 매칭 (캐싱됨)

3. 정규화 (normalizers/)
   ├─ location.py - 주소 정규화
   ├─ salary.py - 연봉 정규화
   ├─ job_type.py - 직무 카테고리
   └─ company.py - 회사명 정규화

4. Firestore 저장 (배치 500건 단위)
```

---

## 유지보수 체크리스트

### HTML 구조 변경 시

잡코리아 HTML이 변경되면 다음을 확인:

- [ ] 목록 페이지 셀렉터 (`article.list-item` 등)
- [ ] 상세 페이지 셀렉터 (`company-address` 등)
- [ ] JSON-LD 스키마 구조
- [ ] 연봉 정보 위치

### 새 필드 추가 시

1. `app/parsers/detail_parser.py`에서:
   - `_parse_XXX()` 메서드 추가
   - `parse()` 반환 딕셔너리에 필드 포함
2. 정규화 필요 시 `app/normalizers/`에 로직 추가
3. Firestore 저장 로직 확인
4. 백엔드 Gemini 서비스에서 해당 필드 사용 가능한지 확인

### 데이터 품질 점검

```python
# Firestore에서 빈 location_full 확인
db.collection("jobs").where("location_full", "==", "").stream()

# company_address는 있지만 location_full 없는 경우
# → update_location_full.py 스크립트 실행
```

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `app/scrapers/jobkorea_v2.py` | V2 크롤러 메인 |
| `app/parsers/detail_parser.py` | 상세 페이지 파서 (JSON-LD/CSS/정규식) |
| `app/workers/detail_worker.py` | 상세 크롤링 오케스트레이터 |
| `app/core/ajax_client.py` | AJAX 클라이언트 + Rate Limiter |
| `app/core/session_manager.py` | 세션/프록시 관리 |
| `app/config.py` | 크롤러 상수 (URL, 타임아웃 등) |
| `app/exceptions.py` | 커스텀 예외 (BlockedError 등) |
| `app/normalizers/*.py` | 데이터 정규화 모듈 |
| `app/db/firestore.py` | Firestore 연결/저장 |

---

## 트러블슈팅

### 위치 기반 검색 결과가 0건일 때

1. Firestore에서 `location_full` 필드 확인
2. 빈 값이 많으면 `company_address`에서 복사 필요
3. `scripts/update_location_full.py` 실행

### 크롤링 데이터가 불완전할 때

1. 상세 페이지 HTML 구조 변경 확인
2. JSON-LD 스키마 존재 여부 확인
3. 네트워크 타임아웃 설정 확인
