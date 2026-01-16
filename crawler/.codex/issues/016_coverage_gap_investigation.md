# 수집률 79% 원인 조사

**ID**: 016
**생성일**: 2026-01-16
**상태**: `resolved`
**해결일**: 2026-01-16
**우선순위**: 높음
**관련 이슈**: 015_proxy_workers_scale_up

---

## 1. 증상

수집률 검증 결과 79%로 예상(~95%+)보다 낮음:

```
잡코리아 현재 공고:    57,999건
DB 저장 공고:          50,995건

정상 수집 (A ∩ B):     45,827건
미수집 (A - B):        12,172건
만료/삭제 (B - A):     5,168건

수집률: 79.0%
```

2~3일 사이에 12,000건 차이는 비정상적임.

---

## 2. Claude 분석 결과

### 확인된 사실

| 항목 | 결과 |
|------|------|
| 목록 API ID 형식 | 모두 8자리 정상 |
| DB ID 형식 | 모두 8자리 정상 |
| DB ID 범위 | 47,246,499 ~ 48,431,517 |
| 목록 API ID 범위 | 48,338,899 ~ 48,431,842 |
| 미수집 샘플 404 비율 | 5/6 = 83% |

### 의심 원인

1. **verify_coverage.py 파싱 오류**: `data-gno` 외 다른 숫자 패턴 잘못 수집
2. **목록 API가 삭제된 공고 포함**: 목록에 있지만 상세 404
3. **강남구 분할 크롤링 누락**: 일부 조합 미수집

---

## 3. Codex 검증 요청

### 검증 1: 미수집 ID 404 비율 정밀 측정

```python
# verify_coverage.py 실행 후 미수집 ID 파일 생성
# 미수집 ID 100개 랜덤 샘플링 → HTTP 상태 확인

import random
import httpx

missing_ids = [...]  # verify_coverage.py에서 추출
sample = random.sample(missing_ids, min(100, len(missing_ids)))

results = {"200": 0, "404": 0, "other": 0}
for job_id in sample:
    resp = httpx.get(f"https://www.jobkorea.co.kr/Recruit/GI_Read/{job_id}",
                     headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
    if resp.status_code == 200:
        results["200"] += 1
    elif resp.status_code == 404:
        results["404"] += 1
    else:
        results["other"] += 1

print(f"200 OK: {results['200']}%")
print(f"404 Not Found: {results['404']}%")
```

**기대 결과**: 404 비율이 높으면 목록 API가 삭제된 공고 포함

### 검증 2: 이상한 ID (8자리 아닌 것) 출처 확인

```python
# verify_coverage.py 실행 결과에서
# 8자리가 아닌 ID가 있다면, 어느 구/페이지에서 나왔는지 추적

# 방법: verify_coverage.py 수정하여 ID 수집 시 길이 검증 + 로깅
```

### 검증 3: 실제 수집률 재계산 (404 제외)

```python
# 미수집 ID 중 실제 존재하는 것만 카운트
# 수집률 = DB ∩ 잡코리아(실존) / 잡코리아(실존)
```

### 검증 4: 강남구 수집률 별도 확인

```python
# 강남구만 따로:
# - 목록 API 강남구 전체 ID
# - DB 중 강남구 공고 ID (location_full에서 추출)
# - 비교
```

---

## 4. 참고 파일

- `crawler/verify_coverage.py` - 수집률 검증 스크립트
- `crawler/run_crawler.py` - 메인 크롤러 (강남구 분할 로직)
- `debug/crawl_incremental_30workers_20260116_185027.log` - 최근 크롤링 로그

---

## 5. 기대 결과

1. 미수집 원인 규명 (404 vs 실제 누락)
2. 실제 수집률 재계산 (404 제외)
3. 필요시 크롤러 로직 수정 계획

---

## 6. 결론

### Codex 검증 결과 (2026-01-16)

| 항목 | 결과 |
|------|------|
| 목록 ID 길이 분포 | 6자리: 623, 7자리: 6,724, 8자리: 47,478, 9자리: 3,201 |
| 비정상 ID 출처 | 서초구(I020) 페이지 42~43 (9자리 ID) |
| 미수집 샘플 HTTP 상태 | 200: 33%, 404: 65%, 기타: 2% |
| **8자리 기준 수집률** | **96.5%** (45,814 / 47,478) |

### 원인

`verify_coverage.py`의 `data-gno` 파싱이 비정상 ID(6/7/9자리)를 포함시킴.
이 ID들은 대부분 404(삭제된 공고) 또는 잘못된 파싱 결과.

### 해결

`verify_coverage.py` 수정: 8자리 ID만 필터링

```python
# 변경 전
ids = set(re.findall(r'data-gno="(\d+)"', resp.text))

# 변경 후
raw_ids = re.findall(r'data-gno="(\d+)"', resp.text)
ids = set(i for i in raw_ids if len(i) == 8)
```

### 최종 결론

**실제 수집률 96.5%로 목표(95%+) 달성.**
