# 상세 수집 재시도 큐 + 프록시 오류 대응 강화

**ID**: 012
**생성일**: 2026-01-16
**상태**: `resolved`
**해결일**: 2026-01-16
**관련 이슈**: 011_proxy_pool_optimization

---

## 1. 증상

- 풀 프록시 운용 시 ProxyError(502)로 상세 수집 실패가 누적됨
- 실패 건이 재시도 없이 바로 실패로 종료되어 정확도 저하

```bash
# 샘플 로그
ProxyError 502 Bad Gateway
```

---

## 2. 원인 분석

- 네트워크/프록시 오류(502, 타임아웃)가 발생해도 재시도 큐가 없음
- TransportError 계열 오류에서 워커 세션 교체가 수행되지 않음
- 상세 수집 실패가 즉시 실패로 확정됨

**관련 파일**:
- `app/scrapers/jobkorea_v2.py`

**원인**:
- 상세 수집 로직에 재시도/세션 교체 경로 부재

---

## 3. 이전 유사 이슈 확인

- [x] `.codex/issues/` 검색 완료
- 검색 키워드: retry, proxy, pool, failure
- 유사 이슈: 011_proxy_pool_optimization
- 이전 해결책과 차이점: 풀 워밍업/세션 교체에 이어, 재시도 큐 추가

---

## 4. 해결 방안

### 선택지 A: 실패 재시도 큐 + TransportError 세션 교체
- 장점: 정확도 향상, 프록시 오류 흡수
- 단점: 실행 시간 증가

### 선택지 B: 현 상태 유지
- 장점: 단순
- 단점: 실패 누적, 정확도 저하

**선택**: A
**이유**: 최초 풀 크롤은 정확도가 우선

---

## 5. 수정 내용

### 변경 전
```python
# app/scrapers/jobkorea_v2.py
results = await asyncio.gather(*tasks, return_exceptions=True)
for result in results:
    if isinstance(result, dict) and result:
        pending_jobs.append(result)
        self.stats.detail_success += 1
    else:
        self.stats.detail_failed += 1
```

### 변경 후
```python
# app/scrapers/jobkorea_v2.py
attempts[job_id] += 1
if attempts[job_id] <= retry_limit:
    retry_queue.append(job_id)
else:
    self.stats.detail_failed += 1
    total_saved["failed"] += 1
```

```python
# app/scrapers/jobkorea_v2.py
except httpx.TransportError:
    await self._handle_proxy_worker_failure(worker_idx, type(e).__name__)

# run_crawl_by_gu.py
scraper.rate_limiter.min_delay = 0.2
scraper.rate_limiter.delay = 0.2
await scraper.crawl_details(..., parallel_batch=6, retry_limit=3)
```

### 변경 파일 체크리스트
- [x] `app/scrapers/jobkorea_v2.py`
- [x] `run_crawl_by_gu.py`

---

## 6. 검증

### 검증 명령어
```bash
python3 - <<'PY'
import ast
from pathlib import Path
ast.parse(Path("crawler/app/scrapers/jobkorea_v2.py").read_text())
print("syntax ok")
PY
```

### 결과
| 항목 | 값 |
|------|-----|
| 문법 검사 | syntax ok |
| 500건 샘플 | 성공 499/500 (99.8%), 실패 1건(404) |

---

## 7. 회고

### 이 문제를 예방하려면?
- 프록시 오류는 재시도/세션 교체로 흡수

### 다음에 참고할 점
- 최초 풀 크롤은 정확도 우선 설정 유지

### 관련 체크리스트 추가 필요?
- [ ] 예 → AGENTS.md 업데이트
- [x] 아니오
