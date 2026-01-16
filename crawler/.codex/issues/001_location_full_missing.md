# location_full 필드 누락

**ID**: 001
**생성일**: 2026-01-13
**상태**: `resolved`
**해결일**: 2026-01-13
**관련 이슈**: 없음 (첫 이슈)

---

## 1. 증상

- 780개 공고 중 653개에서 `location_full` 필드가 비어있음
- 위치 기반 필터링(지하철 통근시간 계산) 작동 안됨

```bash
# 확인 쿼리
db.collection("jobs").where("location_full", "==", "").stream()
# 결과: 653건 (83.7%)
```

---

## 2. 원인 분석

**관련 파일**:
- `app/scrapers/jobkorea_v2.py` - `_parse_detail_page()` 메서드

**원인**:
- `company_address` 변수로 주소를 추출했으나
- 반환 딕셔너리에 `location_full` 키를 포함하지 않음
- Firestore에 해당 필드가 저장되지 않음

**데이터 출처별 현황**:
| 출처 | 필드 | 예시 | 비고 |
|------|------|------|------|
| 목록 페이지 태그 | location_full | "서울 강남구" | 구/군 수준만 제공 |
| 상세 페이지 | company_address | "서울 강남구 테헤란로 123" | 상세 주소 포함 |
| JSON-LD | addressLocality | "서울특별시 강남구" | 가장 정확 |

---

## 3. 이전 유사 이슈 확인

- [x] `.codex/issues/` 검색 완료
- 검색 키워드: location, 위치, 주소
- 유사 이슈: 없음 (첫 이슈)

---

## 4. 해결 방안

### 선택지 A: 반환값에 location_full 직접 추가
- 장점: 간단, 즉시 해결
- 단점: 없음

### 선택지 B: 정규화 단계에서 매핑
- 장점: 로직 분리
- 단점: 복잡도 증가, 불필요한 추상화

**선택**: A
**이유**: 단순한 필드 누락이므로 직접 추가가 적절

---

## 5. 수정 내용

### 변경 전
```python
# app/scrapers/jobkorea_v2.py - _parse_detail_page()

return {
    ...
    "company_address": company_address,
    ...
}
```

### 변경 후
```python
# app/scrapers/jobkorea_v2.py - _parse_detail_page()

# JSON-LD addressLocality 파싱 추가
json_ld_match = re.search(r'"addressLocality"\s*:\s*"([^"]+)"', html)
if json_ld_match:
    company_address = json_ld_match.group(1).strip()

return {
    ...
    "location_full": company_address,  # 추가됨
    "company_address": company_address,
    ...
}
```

### 변경 파일 체크리스트
- [x] `app/scrapers/jobkorea_v2.py`

---

## 6. 검증

### 검증 명령어
```bash
python test_e2e_quality.py
```

### 결과
| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 위치 정보 점수 | 16.3% | 99.7% |
| 빈 location_full | 653건 | 3건 |

### 추가 조치
- 기존 데이터 마이그레이션: `scripts/update_location_full.py`
- `company_address` → `location_full` 복사

---

## 7. 회고

### 이 문제를 예방하려면?
- 새 필드 추가 시 체크리스트 확인:
  - [ ] 파싱에서 추출
  - [ ] 반환 딕셔너리에 포함
  - [ ] 정규화 적용 (필요시)
  - [ ] DB 저장 확인
  - [ ] 프론트엔드/백엔드에서 사용 가능한지 확인

### 다음에 참고할 점
- `_parse_detail_page()` 반환값 변경 시 **모든 필드가 포함되었는지** 확인
- JSON-LD > CSS selector > meta tag 순으로 우선순위 적용

### 관련 체크리스트 추가 필요?
- [x] 예 → AGENTS.md "새 필드 추가 체크리스트" 섹션 추가됨
