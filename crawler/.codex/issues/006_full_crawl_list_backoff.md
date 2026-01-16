# 구별 목록 수집 안정화 (중복 페이지 조기 종료 + 적응형 딜레이)

**ID**: 006
**생성일**: 2026-01-16
**상태**: `resolved`
**해결일**: 2026-01-16
**관련 이슈**: 002_api_pagination_limit

---

## 1. 증상

- 구별 목록 수집이 고정 딜레이(50ms)만 사용
- API 제한 페이지 이후에도 계속 요청하여 중복/차단 위험 증가

```bash
# run_crawl_by_gu.py 내부 고정 sleep
await asyncio.sleep(0.05)
```

---

## 2. 원인 분석

**관련 파일**:
- `run_crawl_by_gu.py` - `crawl_list_with_params()`

**원인**:
- 응답이 반복되는 상황(페이지 제한)에서도 조기 종료 로직 없음
- 403/429에 대한 적응형 속도 제한 없음

---

## 3. 이전 유사 이슈 확인

- [x] `.codex/issues/` 검색 완료
- 검색 키워드: 구별, 분할, pagination
- 유사 이슈: #002 (페이지 제한 발견)
- 이전 해결책과 차이점: 002는 전략 설계, 본 이슈는 구현 안정화

---

## 4. 해결 방안

### 선택지 A: 중복/무효 페이지 감지 후 조기 종료
- 장점: 불필요 요청 감소, 차단 위험 감소
- 단점: 감지 기준 튜닝 필요

### 선택지 B: 적응형 딜레이 + 재시도 적용
- 장점: 차단 대응 향상
- 단점: 수집 시간 증가 가능

**선택**: A + B
**이유**: 안정성/성능 균형을 맞추기 위함

---

## 5. 수정 내용

### 변경 전
```python
# run_crawl_by_gu.py
if resp.status_code == 200:
    matches = re.findall(r'GI_Read/(\d+)', resp.text)
    collected_ids.update(matches)

await asyncio.sleep(0.05)
```

### 변경 후
```python
# run_crawl_by_gu.py
rate_limiter = AdaptiveRateLimiter()
no_new_pages = 0
repeat_pages = 0
last_page_ids = None

if resp.status_code == 200:
    page_ids = set(re.findall(r'GI_Read/(\d+)', resp.text))
    new_ids = page_ids - collected_ids
    collected_ids.update(page_ids)
    if not new_ids:
        no_new_pages += 1
    else:
        no_new_pages = 0

    if last_page_ids is not None and page_ids == last_page_ids:
        repeat_pages += 1
    else:
        repeat_pages = 0
    last_page_ids = page_ids

    if repeat_pages >= 2 or no_new_pages >= 3:
        logger.warning("중복 페이지 감지로 조기 종료")
        break

    rate_limiter.on_success()
else:
    rate_limiter.on_error(resp.status_code)

await asyncio.sleep(rate_limiter.get_delay())
```

### 변경 파일 체크리스트
- [x] `run_crawl_by_gu.py`
- [ ] `app/core/ajax_client.py` (필요 시 import)

---

## 6. 검증

### 검증 명령어
```bash
python run_crawl_by_gu.py
```

### 결과
| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 중복 페이지 요청 | 높음 | 조기 종료 로직 추가 (실전 검증 필요) |
| 차단 위험 | 높음 | 적응형 딜레이 적용 (실전 검증 필요) |

---

## 7. 회고

### 이 문제를 예방하려면?
- API 제한 감지 로직을 기본 수집 루프에 포함

### 다음에 참고할 점
- 조기 종료 기준은 로그로 관찰해 튜닝 필요

### 관련 체크리스트 추가 필요?
- [ ] 예 → AGENTS.md 업데이트
- [ ] 아니오
