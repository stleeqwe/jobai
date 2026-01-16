# 프록시 풀 성능/성공률 최적화

**ID**: 011
**생성일**: 2026-01-16
**상태**: `resolved`
**해결일**: 2026-01-16
**관련 이슈**: 008_single_proxy_pool_fallback, 010_full_crawl_proxy_tuning

---

## 1. 증상

- 풀 프록시 병렬 테스트에서 속도/성공률이 낮음
- 장시간 크롤링 시 단일 프록시 차단 우려가 높음

```bash
# 기존 테스트 요약
# 동일 프록시 10워커: 3.36건/s (20/20)
# 다른 IP 10워커: 0.45건/s (9/10)
```

---

## 2. 원인 분석

- 풀 테스트에서 세션 ID가 8자 규칙을 벗어남
- 풀 모드에서 워커별 쿠키 워밍업이 없고 단일 쿠키 공유
- 풀 모드에서 워커별 차단/실패 시 세션 교체 로직 부재

**관련 파일**:
- `app/scrapers/jobkorea_v2.py`
- `test_proxy_parallel.py`
- `run_crawl_by_gu.py`

**원인**:
- 풀 전략이 고정형(초기 세션 유지)으로만 동작

---

## 3. 이전 유사 이슈 확인

- [x] `.codex/issues/` 검색 완료
- 검색 키워드: proxy, pool, session, warmup
- 유사 이슈: 008, 010
- 이전 해결책과 차이점: 전환 조건/임계값이 아닌 풀 내부 전략 개선

---

## 4. 해결 방안

### 선택지 A: 풀 워커 쿠키 워밍업 + 세션 교체
- 장점: 차단 대응 강화, 풀 안정성 향상
- 단점: 초기 워밍업 시간 증가

### 선택지 B: 풀 전환 자체 비활성화
- 장점: 단순, 속도 유지
- 단점: 장시간 운영 차단 위험

**선택**: A
**이유**: 장시간 운영 안정성을 우선

---

## 5. 수정 내용

### 변경 전
```python
# app/scrapers/jobkorea_v2.py
self.proxy_mode = "single" if use_proxy else "none"
self.proxy_session_lifetime = "10m"

# pool 모드에서도 동일 쿠키 사용
client = httpx.AsyncClient(..., cookies=cookies, proxy=proxy_url)
```

```python
# test_proxy_parallel.py
session_id = f"worker{worker_id}_{random.randint(1000, 9999)}"  # 8자 규칙 위반
```

### 변경 후
```python
# app/scrapers/jobkorea_v2.py
self.proxy_mode = "pool" if proxy_start_pool else "single"
self.proxy_session_lifetime = proxy_session_lifetime
self.proxy_pool_warmup = True

# 풀 워커별 세션 ID 생성(8자) + 쿠키 워밍업
session_id = f"w{worker_id:02d}{rand:05d}"
cookies = await _fetch_proxy_cookies(proxy_url)

# 차단 누적 시 워커 세션 교체
if worker_failures >= proxy_worker_rotate_threshold:
    await _rotate_proxy_worker(worker_idx, reason)
```

```python
# test_proxy_parallel.py
session_id = f"w{worker_id:02d}{random.randint(0, 99999):05d}"
```

### 변경 파일 체크리스트
- [x] `app/scrapers/jobkorea_v2.py`
- [x] `test_proxy_parallel.py`
- [x] `run_crawl_by_gu.py`

---

## 6. 검증

### 검증 명령어
```bash
python3 - <<'PY'
import ast
from pathlib import Path
for path in [
    "crawler/app/scrapers/jobkorea_v2.py",
    "crawler/test_proxy_parallel.py",
    "crawler/run_crawl_by_gu.py",
]:
    ast.parse(Path(path).read_text())
print("syntax ok")
PY
```

### 결과
| 항목 | 값 |
|------|-----|
| 문법 검사 | syntax ok |
| 풀 프록시 10워커 (10건) | 1.1건/s, 성공 10/10 |
| 풀 프록시 10워커 (30건) | 3.9건/s, 성공 20/30 |

---

## 7. 회고

### 이 문제를 예방하려면?
- 풀 프록시 테스트도 운영 규칙(세션 ID 길이, 쿠키 워밍업) 준수

### 다음에 참고할 점
- 풀 성능은 세션 초기화 품질에 좌우됨

### 관련 체크리스트 추가 필요?
- [ ] 예 → AGENTS.md 업데이트
- [x] 아니오
