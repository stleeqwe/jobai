# 상세 수집 워커 패턴 리팩토링

**ID**: 013
**생성일**: 2026-01-16
**상태**: `resolved`
**해결일**: 2026-01-16
**관련 이슈**: 011_proxy_pool_optimization, 012_detail_retry_accuracy

---

## 1. 증상

- 상세 수집 속도가 3.3건/s로 목표(10건/s) 미달
- 배치 단위 `asyncio.gather`에서 느린 요청이 전체 배치를 블로킹

```bash
python run_crawler.py --skip-existing
# debug/crawl_incremental_20260116_165307.log
# [V2] 진행: 100/12590 (3.3건/s, ETA: 62.7분)
```

---

## 2. 원인 분석

- `crawl_details`가 배치 단위로 `asyncio.gather`를 사용해 가장 느린 요청이 다음 배치를 막음
- 워커별 독립 처리(청크 분배)보다 처리량이 떨어짐

**관련 파일**:
- `app/scrapers/jobkorea_v2.py` - `crawl_details()`

**원인**:
- "30개 요청 → 전체 완료 대기 → 다음 배치" 구조로 head-of-line blocking 발생

---

## 3. 이전 유사 이슈 확인

- [x] `.codex/issues/` 검색 완료
- 검색 키워드: parallel, batch, gather, crawl_details
- 유사 이슈: 010_full_crawl_proxy_tuning, 011_proxy_pool_optimization, 012_detail_retry_accuracy
- 이전 해결책과 차이점: 프록시/재시도 튜닝 위주였고, 병렬 패턴 자체 변경은 없음

---

## 4. 해결 방안

### 선택지 A: 배치 gather 유지 + 파라미터 튜닝
- 장점: 변경 범위 최소
- 단점: 느린 요청이 전체 배치 지연, 구조적 병목 유지

### 선택지 B: 워커 패턴으로 리팩토링
- 장점: 워커별 독립 처리로 블로킹 최소화
- 단점: 구조 변경으로 테스트 필요

**선택**: B
**이유**: 병목 원인이 구조적이므로 패턴 변경이 필요

---

## 5. 수정 내용

### 변경 전
```python
for batch_start in range(0, len(pending_ids), current_parallel):
    batch_ids = pending_ids[batch_start:batch_start + current_parallel]
    tasks = [
        self._fetch_detail_with_fallback(job_id, i % self.num_workers)
        for i, job_id in enumerate(batch_ids)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    ...
    await asyncio.sleep(self.rate_limiter.get_delay())
```

### 변경 후
```python
async def _detail_worker(worker_idx: int, ids: List[str], results_queue: asyncio.Queue):
    for job_id in ids:
        result = await self._fetch_detail_with_fallback(job_id, worker_idx)
        await results_queue.put((job_id, result))
        await asyncio.sleep(self.rate_limiter.get_delay())

async def _collect_results(results_queue: asyncio.Queue, active_workers: int):
    while finished_workers < active_workers:
        job_id, result = await results_queue.get()
        # 성공/실패/재시도 처리 + 배치 저장 + 진행률 출력
```

### 변경 파일 체크리스트
- [x] `app/scrapers/jobkorea_v2.py`

---

## 6. 검증

### 검증 명령어
```bash
python test_proxy_parallel.py
```

### 결과
| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 상세 수집 속도(동일 프록시 5워커) | 3.3건/s(운영 로그) | 2.3건/s |
| 상세 수집 속도(다른 IP 5워커) | - | 1.9건/s |
| 상세 수집 속도(프록시 없음 5워커) | - | 10.6건/s |

- 프록시 병렬 속도는 목표(10건/s) 미달, 프록시 없는 환경은 목표 달성

---

## 7. 회고

### 이 문제를 예방하려면?
- 상세 수집 병렬 구조 변경 시 실제 처리량 측정 포함

### 다음에 참고할 점
- 워커 단위 처리로 head-of-line blocking 완화

### 관련 체크리스트 추가 필요?
- [ ] 예 → AGENTS.md 업데이트
- [x] 아니오
