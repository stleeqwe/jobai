# 프록시 병렬 테스트 자격증명 환경변수화

**ID**: 009
**생성일**: 2026-01-16
**상태**: `resolved`
**해결일**: 2026-01-16
**관련 이슈**: 007_proxy_env_config

---

## 1. 증상

- `test_proxy_parallel.py`, `resume_with_proxy.py`, `scripts/enrich_*.py`에 IPRoyal 자격증명이 하드코딩되어 있음
- 테스트/운영 스크립트가 `PROXY_*` 환경변수 흐름과 분리되어 일관성이 없음

```bash
# 파일 내 하드코딩 값 존재
```

---

## 2. 원인 분석

- 스크립트들이 환경변수/설정 로딩 없이 상수로 프록시 정보를 사용

**관련 파일**:
- `test_proxy_parallel.py`
- `resume_with_proxy.py`
- `scripts/enrich_title.py`
- `scripts/enrich_employment_type.py`
- `scripts/enrich_deadline.py`

**원인**:
- 보안/운영 기준에 맞춘 설정 로딩 로직 부재

---

## 3. 이전 유사 이슈 확인

- [x] `.codex/issues/` 검색 완료
- 검색 키워드: proxy, iproyal, 하드코딩
- 유사 이슈: 007_proxy_env_config
- 이전 해결책과 차이점: 007은 크롤러 본체, 본 이슈는 테스트 스크립트

---

## 4. 해결 방안

### 선택지 A: 공용 헬퍼로 PROXY_* 환경변수 사용
- 장점: 보안 개선, 중복 제거, 운영과 동일한 설정 경로
- 단점: 환경변수 미설정 시 스크립트 실행 불가

### 선택지 B: 스크립트별 로컬 파싱 유지
- 장점: 변경 범위 최소
- 단점: 중복 증가, 유지보수 어려움

**선택**: A
**이유**: 중복 제거와 보안 기준 통일

---

## 5. 수정 내용

### 변경 전
```python
# scripts/enrich_title.py
def get_proxy_url() -> str:
    return "http://<user>:<pass>@geo.iproyal.com:12321"
```

### 변경 후
```python
# app/core/proxy_env.py
def get_proxy_url(session_id: Optional[str] = None, lifetime: Optional[str] = None) -> str:
    host, port, username, password = _get_proxy_settings()
    if session_id:
        suffix = f\"_session-{session_id}\"
        if lifetime:
            suffix = f\"{suffix}_lifetime-{lifetime}\"
        password = f\"{password}{suffix}\"
    return f\"http://{username}:{password}@{host}:{port}\"

# scripts/enrich_title.py
proxy_url = get_proxy_url()
```

### 변경 파일 체크리스트
- [x] `app/core/proxy_env.py`
- [x] `test_proxy_parallel.py`
- [x] `resume_with_proxy.py`
- [x] `scripts/enrich_title.py`
- [x] `scripts/enrich_employment_type.py`
- [x] `scripts/enrich_deadline.py`

---

## 6. 검증

### 검증 명령어
```bash
python3 - <<'PY'
import ast
from pathlib import Path
for path in [
    "crawler/app/core/proxy_env.py",
    "crawler/test_proxy_parallel.py",
    "crawler/resume_with_proxy.py",
    "crawler/scripts/enrich_title.py",
    "crawler/scripts/enrich_employment_type.py",
    "crawler/scripts/enrich_deadline.py",
]:
    ast.parse(Path(path).read_text())
print("syntax ok")
PY
```

### 결과
| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 자격증명 노출 | 있음 | 제거 |
| 환경변수 의존 | 없음 | 있음 |
| 문법 검사 | 미실행 | syntax ok |

- 실제 프록시 실행은 `PROXY_*` 환경변수 설정 후 필요

---

## 7. 회고

### 이 문제를 예방하려면?
- 테스트 스크립트도 운영 설정을 그대로 사용하도록 체크리스트화

### 다음에 참고할 점
- 민감정보 하드코딩 방지 리뷰 항목 추가

### 관련 체크리스트 추가 필요?
- [ ] 예 → AGENTS.md 업데이트
- [x] 아니오
