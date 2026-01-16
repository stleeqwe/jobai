# 프록시 자격증명 환경변수화

**ID**: 007
**생성일**: 2026-01-16
**상태**: `resolved`
**해결일**: 2026-01-16
**관련 이슈**: 없음

---

## 1. 증상

- 프록시 계정 정보가 코드에 하드코딩됨
- 보안 리스크 및 회전/운영 관리 어려움

---

## 2. 원인 분석

**관련 파일**:
- `app/core/session_manager.py` - PROXY_* 상수
- `docs/IPROYAL_PROXY.md` - 실제 자격증명 노출

**원인**:
- 환경변수/시크릿 분리를 하지 않고 코드/문서에 직접 기입

---

## 3. 이전 유사 이슈 확인

- [x] `.codex/issues/` 검색 완료
- 검색 키워드: proxy, 프록시
- 유사 이슈: 없음
- 이전 해결책과 차이점: 없음

---

## 4. 해결 방안

### 선택지 A: 환경변수로 이동 + 미설정 시 프록시 비활성화
- 장점: 보안 개선, 운영 유연성
- 단점: 환경 설정 누락 시 프록시 사용 불가

### 선택지 B: 기존 값 유지
- 장점: 즉시 동작
- 단점: 보안 취약점 지속

**선택**: A
**이유**: 보안/운영 리스크가 더 큼

---

## 5. 수정 내용

### 변경 전
```python
# app/core/session_manager.py
PROXY_HOST = "geo.iproyal.com"
PROXY_PORT = 12321
PROXY_USERNAME = "..."
PROXY_PASSWORD = "..."
```

### 변경 후
```python
# app/config.py
PROXY_HOST: str = ""
PROXY_PORT: int = 0
PROXY_USERNAME: str = ""
PROXY_PASSWORD: str = ""
```

```python
# app/core/session_manager.py
PROXY_HOST = settings.PROXY_HOST
PROXY_PORT = settings.PROXY_PORT
PROXY_USERNAME = settings.PROXY_USERNAME
PROXY_PASSWORD = settings.PROXY_PASSWORD

if not self._proxy_configured():
    logger.warning("프록시 설정 누락")
    return None
```

```python
# app/scrapers/jobkorea_v2.py
if (self.proxy_enabled or self.use_proxy) and self.session_manager._proxy_configured():
    proxy_url = f"http://{SessionManager.PROXY_USERNAME}:{SessionManager.PROXY_PASSWORD}@{SessionManager.PROXY_HOST}:{SessionManager.PROXY_PORT}"
else:
    proxy_url = None
```

```bash
# .env.example
PROXY_HOST=
PROXY_PORT=
PROXY_USERNAME=
PROXY_PASSWORD=
```

```markdown
# docs/IPROYAL_PROXY.md
- 실제 자격증명 제거 및 환경변수 사용으로 변경
```

### 변경 파일 체크리스트
- [x] `app/config.py`
- [x] `app/core/session_manager.py`
- [x] `.env.example`
- [x] `docs/IPROYAL_PROXY.md`
- [x] `app/scrapers/jobkorea_v2.py`

---

## 6. 검증

### 검증 명령어
```bash
python run_crawl_500.py
```

### 결과
| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 프록시 사용 | 하드코딩 | 환경변수 기반 (미설정 시 경고) |

---

## 7. 회고

### 이 문제를 예방하려면?
- 자격증명은 코드/문서에 저장하지 않기

### 다음에 참고할 점
- 프록시 미설정 시 폴백 동작을 명확히 경고

### 관련 체크리스트 추가 필요?
- [ ] 예 → AGENTS.md 업데이트
- [ ] 아니오
