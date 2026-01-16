# 상세 수집 실패 로그 개선 및 차단 감지 처리

**ID**: 005
**생성일**: 2026-01-16
**상태**: `resolved`
**해결일**: 2026-01-16
**관련 이슈**: 없음

---

## 1. 증상

- 크롤링 로그에 `상세 파싱 실패 (ID):`만 찍히고 원인 정보가 없음
- HTML 기반 차단(캡차/접근 차단) 감지가 프록시 전환 트리거로 이어지지 않음

```bash
# 로그 예시
DEBUG | crawler.v2 | 상세 파싱 실패 (48338429): 
```

---

## 2. 원인 분석

**관련 파일**:
- `app/scrapers/jobkorea_v2.py` - `_fetch_detail_with_fallback()`, `_fetch_detail_info()`

**원인**:
- 일반 예외에서 타입/상태/본문 길이 등 컨텍스트를 로그에 남기지 않음
- `BlockedError`가 HTTP 상태 코드 처리 흐름에 포함되지 않아 프록시 전환이 발생하지 않음

---

## 3. 이전 유사 이슈 확인

- [x] `.codex/issues/` 검색 완료
- 검색 키워드: 로그, retry, block, 403, 429
- 유사 이슈: 없음
- 이전 해결책과 차이점: 없음

---

## 4. 해결 방안

### 선택지 A: 예외/차단 로그 강화 + BlockedError 처리
- 장점: 원인 파악 가능, 차단 대응 향상
- 단점: 로그가 약간 증가

### 선택지 B: 실패 HTML 저장
- 장점: 100% 재현 가능
- 단점: 저장/보안/비용 부담

**선택**: A
**이유**: 운영 부담 최소화로 원인 파악 가능

---

## 5. 수정 내용

### 변경 전
```python
# jobkorea_v2.py
except Exception as e:
    logger.debug(f"상세 파싱 실패 ({job_id}): {e}")
    return None
```

```python
# jobkorea_v2.py
except Exception as e:
    logger.debug(f"상세 수집 실패 ({job_id}): {e}")
```

### 변경 후
```python
# jobkorea_v2.py
except BlockedError as e:
    self.block_count += 1
    self.rate_limiter.on_error(429)
    if self.block_count >= 5 and self.fallback_to_proxy and not self.proxy_enabled:
        await self._switch_to_proxy()
        client = self.clients[worker_idx]
        return await self._fetch_detail_info(client, job_id)
```

```python
# jobkorea_v2.py
except Exception as e:
    logger.debug(
        "상세 파싱 실패 (%s): %s %s (len=%s)",
        job_id,
        type(e).__name__,
        e,
        len(html),
    )
    return None
```

### 변경 파일 체크리스트
- [x] `app/scrapers/jobkorea_v2.py`

---

## 6. 검증

### 검증 명령어
```bash
python test_v2_crawler.py -v
```

### 결과
| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 실패 로그 가독성 | 낮음 | 타입/길이 포함 로그 추가 |
| 차단 감지 후 프록시 전환 | 미동작 | BlockedError 처리 추가 (실전 검증 필요) |

---

## 7. 회고

### 이 문제를 예방하려면?
- 오류 로그에 타입/상태/본문 길이 포함 규칙화

### 다음에 참고할 점
- BlockedError는 HTTPStatusError와 동일하게 취급 필요

### 관련 체크리스트 추가 필요?
- [ ] 예 → AGENTS.md 업데이트
- [ ] 아니오
