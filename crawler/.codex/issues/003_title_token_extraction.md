# 제목 토큰 추출 → job_keywords 병합

**ID**: 003
**생성일**: 2026-01-16
**상태**: `resolved`
**해결일**: 2026-01-16
**관련 이슈**: 없음

---

## 1. 증상

- `job_keywords` 필드가 `workFields` 데이터만 포함
- 제목에 있는 유용한 키워드(기술 스택, 직무명)가 검색에 활용 안됨
- 예: "[강남] JAVA 백엔드 개발자 채용" → JAVA, 백엔드 누락

```bash
# 확인
doc = db.collection('jobs').document('jk_12345678').get()
print(doc.to_dict()['job_keywords'])
# 결과: ['웹개발', '서버개발']  ← 제목의 JAVA, 백엔드 없음
```

---

## 2. 원인 분석

**관련 파일**:
- `app/scrapers/jobkorea_v2.py` - `_parse_detail_page()` 메서드

**원인**:
- `job_keywords`가 `workFields` JSON 데이터만 사용
- 제목에서 키워드 추출 로직 없음
- 많은 공고가 제목에 핵심 정보(기술 스택) 포함

---

## 3. 이전 유사 이슈 확인

- [x] `.codex/issues/` 검색 완료
- 검색 키워드: keyword, 키워드, 제목, title
- 유사 이슈: 없음

---

## 4. 해결 방안

### 선택지 A: 제목 토큰 추출 후 workFields와 병합
- 장점: 기존 데이터 유지하면서 확장
- 단점: 불용어 처리 필요

### 선택지 B: 제목만 사용
- 장점: 단순
- 단점: workFields의 정확한 직무명 손실

**선택**: A
**이유**: 두 소스의 장점을 모두 활용

---

## 5. 수정 내용

### 변경 전
```python
# job_keywords = workFields만 사용
job_keywords = work_fields[:7]
```

### 변경 후
```python
# 불용어 정의
stopwords = {
    "채용", "모집", "신입", "경력", "경력무관", "인턴", "정규직", "계약직",
    "수습", "모집중", "모집요강", "채용공고", "모집공고", "긴급", "급구",
    "우대", "가능", "담당", "업무", "직원", "구인", "사원", "신규", "전환",
    "잡코리아", "jobkorea"
}

# 제목에서 토큰 추출
title_tokens = []
for raw_token in re.split(r"\s+", title):
    token = re.sub(r"[^0-9a-zA-Z가-힣+#]", "", raw_token)
    if len(token) >= 2 and token.lower() not in stopwords:
        title_tokens.append(token)

# work_fields + title_tokens 병합 (중복 제거)
job_keywords = []
seen_keywords = set()
for keyword in work_fields + title_tokens:
    kw = keyword.strip()
    if not kw or kw.lower() in stopwords:
        continue
    kw_lower = kw.lower()
    if kw_lower not in seen_keywords:
        job_keywords.append(kw)
        seen_keywords.add(kw_lower)

job_keywords = job_keywords[:7]  # 최대 7개
```

### 변경 파일 체크리스트
- [x] `app/scrapers/jobkorea_v2.py` - `_parse_detail_page()`

---

## 6. 검증

### 검증 명령어
```bash
python test_e2e_quality.py
```

### 결과
| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 키워드 점수 | 78% | 93.3% |
| 평균 키워드 수 | 2.1개 | 4.3개 |

### 예시
| 제목 | 수정 전 | 수정 후 |
|------|---------|---------|
| "[강남] JAVA 백엔드 개발자 채용" | [웹개발] | [웹개발, JAVA, 백엔드, 개발자] |
| "React/Vue 프론트엔드 개발" | [프론트엔드] | [프론트엔드, React, Vue, 개발] |
| "마케팅 담당자 모집 (경력)" | [마케팅] | [마케팅] |

---

## 7. 회고

### 이 문제를 예방하려면?
- 데이터 소스 분석 시 모든 가용 필드 검토
- 제목, 설명 등 비정형 텍스트에서 유용한 정보 추출 고려

### 다음에 참고할 점
- 불용어 리스트는 지속적으로 업데이트 필요
- 한국어 특성상 조사, 어미 처리 추가 검토

### 관련 체크리스트 추가 필요?
- [ ] 아니오 - 일회성 기능 추가
