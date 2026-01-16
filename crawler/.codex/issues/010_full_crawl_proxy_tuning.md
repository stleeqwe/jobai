# 풀 크롤링 프록시 전환 기준 튜닝

**ID**: 010
**생성일**: 2026-01-16
**상태**: `resolved`
**해결일**: 2026-01-16
**관련 이슈**: 008_single_proxy_pool_fallback

---

## 1. 증상

- 풀 크롤링(7만건) 목표 3~6시간 대비 프록시 풀 성능 저하
- 속도 저하 기준(3건/s)으로 풀 전환 시 전체 처리량 급락 위험

```bash
# 프록시 병렬 테스트 (요약)
# 동일 프록시 10워커: 3.36건/s
# 다른 IP 10워커: 0.45건/s, 성공 9/10
```

---

## 2. 원인 분석

- 프록시 풀(다른 IP) 성능/성공률이 낮아 전환 시 속도 급락
- 현재 전환 기준이 3건/s로 경계값 근처에서 불필요 전환 가능

**관련 파일**:
- `run_crawl_by_gu.py`
- `app/scrapers/jobkorea_v2.py`

**원인**:
- 운영 스크립트에서 속도 전환 임계값 조정이 없음

---

## 3. 이전 유사 이슈 확인

- [x] `.codex/issues/` 검색 완료
- 검색 키워드: proxy, speed, 전환
- 유사 이슈: 008_single_proxy_pool_fallback
- 이전 해결책과 차이점: 전환 로직 자체는 유지, 임계값 튜닝

---

## 4. 해결 방안

### 선택지 A: 속도 임계값 하향 + 전환 지연 강화
- 장점: 불필요한 풀 전환 억제, 처리량 유지
- 단점: 실제 차단 시 전환이 늦어질 수 있음

### 선택지 B: 풀 전환 비활성화
- 장점: 안정적 처리량 유지
- 단점: 실제 차단 시 회복 불가

**선택**: A
**이유**: 차단 시에는 유지, 평시에는 단일 프록시 유지

---

## 5. 수정 내용

### 변경 전
```python
# run_crawl_by_gu.py
scraper = JobKoreaScraperV2(
    num_workers=10,
    use_proxy=True,
    fallback_to_proxy=True,
    proxy_pool_size=10,
)
```

### 변경 후
```python
# run_crawl_by_gu.py
scraper = JobKoreaScraperV2(
    num_workers=10,
    use_proxy=True,
    fallback_to_proxy=True,
    proxy_pool_size=10,
    proxy_speed_threshold=2.0,
    proxy_delay_threshold=1.0,
    proxy_speed_consecutive=3,
    proxy_speed_warmup=500,
)
```

### 변경 파일 체크리스트
- [x] `run_crawl_by_gu.py`

---

## 6. 검증

### 검증 명령어
```bash
env PROXY_HOST=... PROXY_PORT=... PROXY_USERNAME=... PROXY_PASSWORD=... \
python3 - <<'PY'
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path('crawler').resolve()))
from test_proxy_parallel import test_parallel_same_proxy, test_parallel_different_sessions

async def main():
    await test_parallel_same_proxy(10, 20)
    await test_parallel_different_sessions(10, 10)
asyncio.run(main())
PY
```

### 결과
| 항목 | 값 |
|------|-----|
| 동일 프록시 10워커 | 3.36건/s (20/20) |
| 다른 IP 10워커 | 0.45건/s (9/10) |

---

## 7. 회고

### 이 문제를 예방하려면?
- 전환 기준은 실제 성능 측정 후 튜닝

### 다음에 참고할 점
- 프록시 풀 성능이 낮으면 전환을 보수적으로 설정

### 관련 체크리스트 추가 필요?
- [ ] 예 → AGENTS.md 업데이트
- [x] 아니오
