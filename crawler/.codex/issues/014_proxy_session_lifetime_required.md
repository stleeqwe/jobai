# 프록시 세션 lifetime 필수화

**ID**: 014
**생성일**: 2026-01-16
**상태**: `resolved`
**해결일**: 2026-01-16
**관련 이슈**: 009_proxy_test_env, 011_proxy_pool_optimization

---

## 1. 증상

- 프록시 병렬 테스트에서 "다른 IP 5워커"가 "동일 프록시"보다 느림
- IPRoyal sticky 세션 파라미터 누락 의심

```bash
python test_proxy_parallel.py
# 다른 IP 5워커: 1.9건/s < 동일 프록시 5워커: 2.3건/s
```

---

## 2. 원인 분석

- `get_proxy_url(session_id=...)` 호출 시 `lifetime`이 기본 None이라 suffix에 포함되지 않음
- IPRoyal sticky 세션은 `_session-`과 `_lifetime-`이 함께 있어야 정상 동작

**관련 파일**:
- `app/core/proxy_env.py`
- `test_proxy_parallel.py`

**원인**:
- session_id가 있을 때 lifetime이 누락되며 sticky 세션 규칙 위반

---

## 3. 이전 유사 이슈 확인

- [x] `.codex/issues/` 검색 완료
- 검색 키워드: lifetime, session, sticky, IPRoyal
- 유사 이슈: 009_proxy_test_env, 011_proxy_pool_optimization
- 이전 해결책과 차이점: 자격증명/세션 ID 규칙 개선 이슈였고 lifetime 필수화는 없음

---

## 4. 해결 방안

### 선택지 A: lifetime 기본값 부여 + session_id 사용 시 항상 포함
- 장점: 호출부 최소 변경, sticky 규칙 준수
- 단점: lifetime 커스터마이즈가 숨겨질 수 있음

### 선택지 B: session_id 사용 시 lifetime 미지정이면 에러
- 장점: 규칙 위반 즉시 감지
- 단점: 호출부 수정 범위 확대

**선택**: A
**이유**: 현재 테스트/운영 호출 구조에서 최소 변경으로 규칙 준수

---

## 5. 수정 내용

### 변경 전
```python
# app/core/proxy_env.py
def get_proxy_url(session_id: Optional[str] = None, lifetime: Optional[str] = None) -> str:
    ...
    if session_id:
        suffix = f"_session-{session_id}"
        if lifetime:
            suffix = f"{suffix}_lifetime-{lifetime}"
```

```python
# test_proxy_parallel.py
proxy_url = get_proxy_url(session_id=session_id)
```

### 변경 후
```python
# app/core/proxy_env.py
def get_proxy_url(session_id: Optional[str] = None, lifetime: str = "10m") -> str:
    ...
    if session_id:
        suffix = f"_session-{session_id}_lifetime-{lifetime}"
```

```python
# test_proxy_parallel.py
proxy_url = get_proxy_url(session_id=session_id, lifetime="10m")
```

### 변경 파일 체크리스트
- [x] `app/core/proxy_env.py`
- [x] `test_proxy_parallel.py`

---

## 6. 검증

### 검증 명령어
```bash
set -a
source .env
set +a
./venv/bin/python test_proxy_parallel.py
```

### 결과
| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 다른 IP 5워커 | 1.9건/s | 2.3건/s |
| 동일 프록시 5워커 | 2.3건/s | 1.0건/s |
| 프록시 없음 5워커 | 10.6건/s | 12.4건/s |

---

## 7. 회고

### 이 문제를 예방하려면?
- 프록시 규칙(세션 + lifetime)을 테스트 코드에 명시

### 다음에 참고할 점
- sticky 세션 파라미터는 누락 시 성능에 직접 영향

### 관련 체크리스트 추가 필요?
- [ ] 예 → AGENTS.md 업데이트
- [x] 아니오
