# Firestore 프로젝트 설정 누락으로 품질 테스트 실패

**ID**: 004
**생성일**: 2026-01-16
**상태**: `resolved`
**해결일**: 2026-01-16
**관련 이슈**: 없음

---

## 1. 증상

- `test_e2e_quality.py` 실행 시 Firestore RunQuery에서 400 오류 발생
- 데이터 품질 점검 자체가 불가능

```bash
python test_e2e_quality.py
# google.api_core.exceptions.InvalidArgument: 400 ... RESOURCE_PROJECT_INVALID
```

---

## 2. 원인 분석

**관련 파일**:
- `app/db/firestore.py` - `get_db()`
- `test_e2e_quality.py` - Firestore 조회 시작부

**원인**:
- `settings.GOOGLE_CLOUD_PROJECT`가 비어 있어 빈 프로젝트 ID로 클라이언트를 생성
- Firestore가 `RESOURCE_PROJECT_INVALID`로 요청을 거부

---

## 3. 이전 유사 이슈 확인

- [x] `.codex/issues/` 검색 완료
- 검색 키워드: firestore, project, 환경
- 유사 이슈: 없음
- 이전 해결책과 차이점: 없음

---

## 4. 해결 방안

### 선택지 A: 설정 누락 시 명시적으로 에러 처리
- 장점: 원인 파악이 즉시 가능
- 단점: 로컬 실행이 설정 없으면 중단됨

### 선택지 B: 프로젝트 값이 없으면 자동 추론(ADC/서비스계정)
- 장점: 유연성 유지, 기존 환경과 호환
- 단점: 여전히 환경 의존성이 있음

**선택**: B + 최소 가드
**이유**: 빈 프로젝트로 요청하는 실패를 제거하면서도 ADC 환경을 허용

---

## 5. 수정 내용

### 변경 전
```python
# app/db/firestore.py
if credentials_path:
    credentials = service_account.Credentials.from_service_account_file(
        credentials_path
    )
    _db = firestore.Client(
        project=settings.GOOGLE_CLOUD_PROJECT,
        credentials=credentials
    )
else:
    _db = firestore.Client(project=settings.GOOGLE_CLOUD_PROJECT)
```

### 변경 후
```python
# app/db/firestore.py
project = settings.GOOGLE_CLOUD_PROJECT or None
if credentials_path:
    credentials = service_account.Credentials.from_service_account_file(
        credentials_path
    )
    project = project or getattr(credentials, "project_id", None)
    _db = firestore.Client(project=project, credentials=credentials)
else:
    _db = firestore.Client(project=project) if project else firestore.Client()
```

```python
# test_e2e_quality.py
if not settings.GOOGLE_CLOUD_PROJECT and not settings.GOOGLE_APPLICATION_CREDENTIALS:
    print("[Error] GOOGLE_CLOUD_PROJECT 또는 GOOGLE_APPLICATION_CREDENTIALS 설정 필요")
    return
```

```bash
# .env.example
GOOGLE_CLOUD_PROJECT=
GOOGLE_APPLICATION_CREDENTIALS=
```

### 변경 파일 체크리스트
- [x] `app/db/firestore.py`
- [x] `test_e2e_quality.py`
- [ ] `.env.example`

---

## 6. 검증

### 검증 명령어
```bash
python test_e2e_quality.py
```

### 결과
| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 품질 점수 | 실행 실패 | (환경 설정 후 확인) |
| 오류 | RESOURCE_PROJECT_INVALID | 설정 누락 경고 출력 후 종료 |

---

## 7. 회고

### 이 문제를 예방하려면?
- 테스트 실행 전 환경변수 누락 체크

### 다음에 참고할 점
- 프로젝트 ID가 비어 있으면 Firestore 요청이 즉시 실패함

### 관련 체크리스트 추가 필요?
- [ ] 예 → AGENTS.md 업데이트
- [ ] 아니오
