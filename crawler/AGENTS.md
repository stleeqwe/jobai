# Crawler Agent Instructions

> **목적**: 코드 수정 전 반드시 이슈 기록을 통한 체계적 형상관리
> **최종 업데이트**: 2026-01-16

---

## 🔀 작업 요청 경로

Codex는 **두 가지 경로**로 작업 요청을 받습니다:

| 경로 | 트리거 | 특징 |
|------|--------|------|
| **A. 직접 요청** | 사용자가 Codex 직접 호출 | 독립 작업, 기존 Step 1~7 절차 |
| **B. 협업 요청** | Claude가 분석 후 위임 | Claude 분석 검토 + 추가 분석 |

### 경로 판단

```
요청 수신 → "[Codex 협업 요청]" 형식인가?
              │
         Yes  │  No
              ↓   ↓
         경로 B   경로 A
        (협업)   (직접)
```

---

## 🅰️ 경로 A: 직접 요청 (사용자 → Codex)

사용자가 직접 Codex를 호출한 경우, **기존 Step 1~7 절차**를 따릅니다.

→ 아래 "절대 규칙" 섹션의 Step 1~7 참조

---

## 🅱️ 경로 B: Claude-Codex 협업

Claude가 전방위 분석 후 크롤러 수정이 필요하다고 판단하면 협업 요청을 보냅니다.

### 역할 분담

| 역할 | Claude | Codex (나) |
|------|--------|------------|
| 크롤러 코드 읽기/분석 | ✓ | ✓ |
| 전방위 원인 추적 (프론트→백엔드→크롤러) | ✓ | |
| 가설 수립 및 공유 | ✓ | |
| **추가 분석 및 검증** | | ✓ |
| **수정 계획 도출** | 협업 | 협업 |
| **코드 수정** | | ✓ |
| **이슈 기록** | | ✓ |
| **테스트 실행** | | ✓ |

### 협업 요청 수신 시 워크플로우

Claude로부터 `[Codex 협업 요청]`을 수신하면:

```
1. Claude 분석 결과 검토
   - 가설이 타당한지 확인
   - 추적 경로가 맞는지 검토

2. 자체 추가 분석
   - Claude가 놓친 부분 있는지 확인
   - 다른 원인 가능성 검토
   - 기존 이슈 히스토리 조회

3. 분석 결과 공유
   - Claude 가설에 동의/반박
   - 추가 발견 사항 공유
   - 수정 계획 제안

4. 합의 후 수정 진행
   - 이슈 생성 (Step 3~)
   - 코드 수정
   - 검증
```

### 협업 요청 형식 (수신)

```
[Codex 협업 요청]

## 1. 상황
(문제 증상, 발생 경위)

## 2. Claude 분석 결과
- 추적 경로: 프론트 → 백엔드 → 크롤러
- 의심 원인: (구체적 파일:라인, 로직 설명)
- 가설: "~한 이유로 ~가 발생한 것 같다"

## 3. Codex 추가 검토 요청
- [ ] 위 가설이 맞는지 검증해줘
- [ ] 다른 원인이 있을 수 있는지 확인해줘
- [ ] 관련 기존 이슈 있는지 조회해줘
```

### 협업 응답 형식 (발신)

```
[Codex 분석 결과]

## 1. Claude 가설 검토
- 동의/반박: (근거와 함께)

## 2. 추가 발견 사항
- (있다면 기술)

## 3. 기존 이슈 조회 결과
- 유사 이슈: (있다면 번호와 요약)

## 4. 수정 계획 제안
- 수정 대상: (파일:라인)
- 수정 내용: (요약)
- 예상 영향: (범위)

## 5. 다음 단계
- [ ] 이 계획으로 진행해도 될까요?
```

---

## 🚨 절대 규칙: 코드 수정 전 이슈 먼저

**어떤 코드 수정 요청이든 아래 순서를 반드시 따를 것.**
**이 규칙을 건너뛰면 안 됨.**

```
협업 요청/직접 요청 수신 → [Step 1~2] 진단 & 기존 이슈 조회 → [Step 3] 이슈 생성
                        → [Step 4] 수정 내용 먼저 기록 → [Step 5] 코드 수정
                        → [Step 6] 검증 → [Step 7] 이슈 닫기
```

---

## Step 1: 문제 파악

```bash
# 빈 필드 확인 예시
python -c "
from app.db.firestore import get_db
db = get_db()
field = 'location_full'  # 확인할 필드
empty = list(db.collection('jobs').where(field, '==', '').limit(10).stream())
print(f'빈 {field}: {len(empty)}건')
for doc in empty[:3]:
    print(f'  - {doc.id}')
"

# 최근 크롤링 로그 확인
tail -100 crawl_*.log | grep -i error
```

**질문해야 할 것:**
- 어떤 데이터가 비거나 잘못되었나?
- 언제부터 발생했나?
- 영향받은 범위는?

---

## Step 2: 기존 이슈 조회 (필수!)

```bash
# 이슈 목록 확인
ls -la .codex/issues/

# 키워드로 검색
grep -ri "키워드" .codex/issues/

# 예: location 관련 이슈 검색
grep -ri "location\|위치\|주소" .codex/issues/

# 예: 파싱 관련 이슈 검색  
grep -ri "파싱\|selector\|셀렉터\|JSON-LD" .codex/issues/

# 예: 빈 값 관련 이슈 검색
grep -ri "empty\|missing\|빈\|누락" .codex/issues/
```

**확인 사항:**
- [ ] 유사한 이슈가 있었는가?
- [ ] 있다면 그때 어떻게 해결했는가?
- [ ] 이번 문제와 차이점은?

---

## Step 3: 새 이슈 생성

유사 이슈가 없거나 다른 원인이면 새 이슈 생성:

```bash
# 다음 이슈 번호 확인
ls .codex/issues/ | grep -E "^[0-9]+" | sort -n | tail -1

# 새 이슈 파일 생성 (템플릿 복사)
cp .codex/issues/_TEMPLATE.md .codex/issues/NNN_이슈제목.md
```

**파일명 규칙**: `NNN_간단한_설명.md`
- 예: `004_company_name_json_ld_fail.md`
- 예: `005_salary_new_pattern.md`

---

## Step 4: 이슈 파일에 수정 내용 먼저 작성

**코드를 수정하기 전에** 이슈 파일의 섹션 5에 작성:

```markdown
## 5. 수정 내용

### 변경 전
```python
# 현재 코드 복사
```

### 변경 후
```python
# 수정할 코드 작성
```
```

**이 단계를 건너뛰고 바로 코드 수정하면 안 됨!**

---

## Step 5: 코드 수정

이슈 파일 작성 완료 후 실제 코드 수정 진행.

---

## Step 6: 검증 (필수!)

```bash
# 품질 검증
cd crawler && source venv/bin/activate
python test_e2e_quality.py

# 특정 필드 검증
python -c "
from app.db.firestore import get_db
db = get_db()
# 수정 후 빈 값 확인
"
```

**이슈 파일에 결과 기록:**
```markdown
## 6. 검증

### 결과
| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 품질 점수 | 85% | 92% |
| 빈 location_full | 653건 | 3건 |
```

---

## Step 7: 이슈 닫기

```markdown
**상태**: `resolved`
**해결일**: 2026-01-16
```

---

## 파일별 수정 주의사항

| 파일 | 역할 | 수정 시 체크 |
|------|------|-------------|
| `app/scrapers/jobkorea_v2.py` | 메인 크롤러 (오케스트레이션) | 이슈 필수, 테스트 필수 |
| `app/parsers/detail_parser.py` | 상세 페이지 파싱 (JSON-LD/CSS/정규식) | 셀렉터/패턴 변경 주의 |
| `app/workers/detail_worker.py` | 상세 크롤링 오케스트레이터 | 병렬 로직 주의 |
| `app/config.py` | 크롤러 상수 (URL, 타임아웃) | 관련 파일 영향 확인 |
| `app/exceptions.py` | 커스텀 예외 | 에러 핸들링 영향 확인 |
| `app/normalizers/salary.py` | 급여 파싱 | 새 패턴 추가 시 이슈 기록 |
| `app/normalizers/location.py` | 지역 정규화 | 매핑 추가 시 이슈 기록 |
| `app/normalizers/job_type.py` | 직무 카테고리 | 매핑 추가 시 이슈 기록 |
| `app/core/ajax_client.py` | AJAX 호출 + Rate Limiter | API 변경 시 이슈 기록 |
| `app/core/session_manager.py` | 세션/프록시 관리 | 인증 로직 주의 |
| `app/db/firestore.py` | DB 저장 | 필드 추가/변경 시 이슈 기록 |

---

## 자주 발생하는 문제 패턴

### 1. 빈 필드 문제
**검색**: `grep -ri "empty\|missing\|빈\|누락" .codex/issues/`

**주요 원인**:
- `DetailPageParser.parse()` 반환값에 필드 누락
- JSON-LD 구조 변경
- CSS 셀렉터 변경
- 정규식 패턴 매칭 실패

**체크리스트**:
- [ ] `app/parsers/detail_parser.py`의 `_parse_XXX()` 메서드 확인
- [ ] `_PATTERNS` 딕셔너리의 정규식 패턴 확인
- [ ] CSS 셀렉터 폴백 있는가?
- [ ] `parse()` 반환 딕셔너리에 필드 포함했는가?

### 2. 셀렉터/파싱 실패
**검색**: `grep -ri "selector\|셀렉터\|파싱\|parse" .codex/issues/`

**진단 방법**:
```bash
# 실제 HTML 확인
curl -s "https://www.jobkorea.co.kr/Recruit/GI_Read/JOB_ID" | head -500
# 또는 브라우저 개발자 도구 사용
```

**주요 원인**:
- 잡코리아 HTML 구조 변경
- 새로운 페이지 템플릿 추가
- JSON-LD 스키마 변경

**수정 대상 파일**: `app/parsers/detail_parser.py`

### 3. 차단/Rate Limit
**검색**: `grep -ri "block\|차단\|429\|403" .codex/issues/`

**주요 원인**:
- 요청 속도 과다
- 세션 만료
- IP 차단

**대응**:
- `AdaptiveRateLimiter` 자동 감속
- 프록시 폴백 (5회 연속 실패 시)

---

## 새 필드 추가 체크리스트

`app/parsers/detail_parser.py`에 새 필드 추가 시:

- [ ] `_PATTERNS` 딕셔너리에 정규식 패턴 추가 (모듈 레벨에서 컴파일)
- [ ] `_parse_XXX()` 메서드 구현 (JSON-LD 우선, CSS 셀렉터 폴백)
- [ ] `parse()` 메서드 반환 딕셔너리에 포함
- [ ] 정규화 필요 시 `app/normalizers/`에 로직 추가
- [ ] `test_e2e_quality.py`에 검증 추가
- [ ] 이슈 파일에 기록

---

## 검증 명령어 모음

```bash
# 전체 품질 검증
python test_e2e_quality.py

# 크롤러 단위 테스트
python -m pytest test_v2_crawler.py -v

# 특정 공고 상세 확인
python -c "
from app.db.firestore import get_db
db = get_db()
doc = db.collection('jobs').document('jk_12345678').get()
print(doc.to_dict())
"

# 필드별 빈 값 통계
python -c "
from app.db.firestore import get_db
db = get_db()
fields = ['location_full', 'company_name', 'title', 'salary_text']
for f in fields:
    empty = len(list(db.collection('jobs').where(f, '==', '').limit(1000).stream()))
    print(f'{f}: {empty}건 빈 값')
"
```

---

## 디렉토리 구조

```
crawler/
├── .codex/
│   └── issues/                 # 이슈 기록 (핵심!)
│       ├── _TEMPLATE.md
│       ├── 001_location_full_missing.md
│       └── ...
├── AGENTS.md                   # 이 파일 (Codex 자동 로드)
├── app/                        # 운영 코드
│   ├── config.py               # 크롤러 상수 중앙화
│   ├── exceptions.py           # 커스텀 예외 (BlockedError 등)
│   ├── scrapers/
│   │   └── jobkorea_v2.py      # V2 메인 크롤러
│   ├── parsers/                # 파싱 모듈
│   │   └── detail_parser.py    # 상세 페이지 파서
│   ├── workers/                # 워커 모듈
│   │   └── detail_worker.py    # 상세 크롤링 오케스트레이터
│   ├── core/                   # 핵심 유틸
│   │   ├── ajax_client.py      # AJAX 클라이언트
│   │   └── session_manager.py  # 세션/프록시 관리
│   ├── normalizers/            # 데이터 정규화
│   └── db/                     # DB 연동
├── tests/                      # 테스트
│   ├── unit/                   # 단위 테스트
│   ├── integration/            # 통합 테스트
│   └── e2e/                    # E2E 테스트
└── docs/
    └── CRAWLER.md              # 기술 문서
```

---

## 금지 사항

1. **이슈 파일 없이 코드 수정 금지**
2. **기존 이슈 검색 없이 새 이슈 생성 금지**
3. **검증 없이 수정 완료 처리 금지**
4. **테스트 파일 루트에 생성 금지** → `tests/` 사용
