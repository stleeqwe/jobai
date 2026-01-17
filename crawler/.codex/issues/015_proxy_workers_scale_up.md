# 프록시 워커 수 확대

**ID**: 015
**생성일**: 2026-01-16
**상태**: `resolved`
**해결일**: 2026-01-16
**관련 이슈**: 010_full_crawl_proxy_tuning, 011_proxy_pool_optimization, 014_proxy_session_lifetime_required

---

## 1. 증상

- 레지덴셜 프록시 평균 latency(약 2.2초/요청)로 처리량이 목표(10건/s)에 미달
- 병렬 실행 자체는 정상 동작

---

## 2. 원인 분석

- 프록시 응답 지연이 고정적이어서 워커 수 확대로 처리량 보완 필요

**관련 파일**:
- `run_crawler.py`

**원인**:
- 워커 수(10)와 프록시 풀 크기(10)가 병렬 처리량 상한을 제한

---

## 3. 이전 유사 이슈 확인

- [x] `.codex/issues/` 검색 완료
- 검색 키워드: num_workers, proxy, pool
- 유사 이슈: 010_full_crawl_proxy_tuning, 011_proxy_pool_optimization
- 이전 해결책과 차이점: 전환/세션 최적화 위주였고, 워커 수 증가는 없음

---

## 4. 해결 방안

### 선택지 A: 워커/프록시 풀 크기 확대 (10 → 30)
- 장점: 처리량 상한 상승
- 단점: 프록시 비용/차단 리스크 증가 가능

### 선택지 B: 현 상태 유지
- 장점: 안정성 유지
- 단점: 목표 처리량 미달

**선택**: A
**이유**: 레이턴시 한계를 병렬성으로 보완

---

## 5. 수정 내용

### 변경 전
```python
# run_crawler.py
scraper = JobKoreaScraperV2(
    num_workers=10,
    use_proxy=True,
    fallback_to_proxy=True,
    proxy_pool_size=10,
    proxy_start_pool=True,
    proxy_pool_warmup=True,
    proxy_worker_rotate_threshold=2,
    proxy_session_lifetime="30m",
    proxy_speed_threshold=2.0,
    proxy_delay_threshold=1.0,
    proxy_speed_consecutive=3,
    proxy_speed_warmup=500,
)
```

### 변경 후
```python
# run_crawler.py
scraper = JobKoreaScraperV2(
    num_workers=30,
    use_proxy=True,
    fallback_to_proxy=True,
    proxy_pool_size=30,
    proxy_start_pool=True,
    proxy_pool_warmup=True,
    proxy_worker_rotate_threshold=2,
    proxy_session_lifetime="30m",
    proxy_speed_threshold=2.0,
    proxy_delay_threshold=1.0,
    proxy_speed_consecutive=3,
    proxy_speed_warmup=500,
)
```

### 변경 파일 체크리스트
- [x] `run_crawler.py`

---

## 6. 검증

### 검증 명령어
```bash
./venv/bin/python run_crawler.py --skip-existing
```

### 결과
| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 전체 평균 속도 | 3.3건/s | 5.8건/s |
| 상세 수집 순간 속도 | - | 12.6~18.0건/s |
| 상세 성공 | - | 8,622건 |
| 신규 저장 | - | 8,575건 |
| 업데이트 | - | 47건 |

- 소요: 24.7분 (전체 기준)

---

## 7. 회고

### 이 문제를 예방하려면?
- 프록시 레이턴시 기반 처리량 산정 후 워커 수를 사전 계산

### 다음에 참고할 점
- 병렬성 확대로 처리량 상한을 보완

### 관련 체크리스트 추가 필요?
- [ ] 예 → AGENTS.md 업데이트
- [x] 아니오
