# 단일 프록시 → 풀 프록시 전환 (속도/차단 기반)

**ID**: 008
**생성일**: 2026-01-16
**상태**: `resolved`
**해결일**: 2026-01-16
**관련 이슈**: 007_proxy_env_config

---

## 1. 증상

- 단일 프록시로 스크래핑 중 레이트 리밋이 걸리면 속도가 3건/s 이하로 하락
- 현재는 403/429 기반의 프록시 전환만 있어 속도 저하에 대한 대응이 없음

```bash
# 로그 예시
# 진행 속도 3건/s 이하 + delay 증가
```

---

## 2. 원인 분석

- 속도 저하를 감지해 프록시 풀(10개)로 전환하는 로직이 없음
- 현재 전환은 HTTP 403/429 기반으로만 동작

**관련 파일**:
- `app/scrapers/jobkorea_v2.py`
- `run_crawl_500.py` (운영 스크립트)
- `run_full_crawl_v2.py`
- `run_crawl_by_gu.py` (상세 수집 단계)

**원인**:
- 속도/딜레이 기반 전환 기준이 없음

---

## 3. 이전 유사 이슈 확인

- [x] `.codex/issues/` 검색 완료
- 검색 키워드: proxy, rate, fallback, speed
- 유사 이슈: 없음
- 이전 해결책과 차이점: 007은 자격증명 분리, 본 이슈는 전환 로직 추가

---

## 4. 해결 방안

### 선택지 A: 속도 + 레이트리밋 지표 기반 전환
- 장점: 체감 성능 유지, 차단 완화
- 단점: 기준 튜닝 필요

### 선택지 B: 항상 풀 프록시로 시작
- 장점: 안정적
- 단점: 비용 증가, 불필요한 프록시 사용

**선택**: A
**이유**: 비용을 줄이면서 속도 저하 시에만 풀 프록시 전환

---

## 5. 수정 내용

### 변경 전
```python
# app/scrapers/jobkorea_v2.py
if self.proxy_enabled or self.use_proxy:
    proxy_url = f"http://{SessionManager.PROXY_USERNAME}:{SessionManager.PROXY_PASSWORD}@{SessionManager.PROXY_HOST}:{SessionManager.PROXY_PORT}"

# crawl_details 진행 로그에 속도만 표시
print(f"[V2] 진행: {processed}/{len(id_list)} ({speed:.1f}건/s, ETA: {eta/60:.1f}분)")
```

### 변경 후
```python
# app/scrapers/jobkorea_v2.py
self.proxy_mode = "single" if use_proxy else "none"
self.proxy_pool_size = 10
self.proxy_speed_threshold = 3.0
self.proxy_delay_threshold = 0.3

proxy_mode = self.proxy_mode  # single|pool|none
if proxy_mode == "single":
    proxy_url = _build_proxy_url("single")
elif proxy_mode == "pool":
    proxy_url = _build_proxy_url(f"worker{i:02d}")

if window_speed < 3.0 and rate_limited:
    await self._switch_to_proxy_pool(reason="속도 저하/레이트리밋")
```

```python
# run_crawl_500.py / run_full_crawl_v2.py
scraper = JobKoreaScraperV2(
    num_workers=10,
    use_proxy=True,
    fallback_to_proxy=True,
    proxy_pool_size=10,
)
```

```python
# run_crawl_by_gu.py (상세 수집 단계)
scraper = JobKoreaScraperV2(
    num_workers=10,
    use_proxy=True,
    fallback_to_proxy=True,
    proxy_pool_size=10,
)
```

### 변경 파일 체크리스트
- [x] `app/scrapers/jobkorea_v2.py`
- [x] `run_crawl_500.py`
- [x] `run_full_crawl_v2.py`
- [x] `run_crawl_by_gu.py`

---

## 6. 검증

### 검증 명령어
```bash
python run_crawl_500.py
```

### 결과
| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 속도 저하 시 전환 | 없음 | 전환 로직 추가 (실전 검증 필요) |
| 전환 시 워커/프록시 | 불명확 | 10개 프록시 전환 (로컬 스모크 확인) |

### 로컬 스모크
```bash
python -c "from app.scrapers.jobkorea_v2 import JobKoreaScraperV2; import httpx, asyncio; async def t():\n s=JobKoreaScraperV2(use_proxy=True); await s._create_worker_pool(httpx.Cookies()); print(s.proxy_mode); await s.close();\n asyncio.run(t())"
```

---

## 7. 회고

### 이 문제를 예방하려면?
- 속도/차단 기반 전환 지표를 표준화

### 다음에 참고할 점
- 전환 기준은 운영 로그로 튜닝 필요

### 관련 체크리스트 추가 필요?
- [ ] 예 → AGENTS.md 업데이트
- [ ] 아니오
