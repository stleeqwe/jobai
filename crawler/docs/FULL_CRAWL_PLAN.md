# 풀 크롤링 계획서

> 서울 전체 채용공고 수집 (로컬 실행)

## 현황 분석

### 현재 상태
- **DB 공고 수**: 12,140건
- **목표**: ~77,000건 (서울 전체)
- **예상 신규**: ~65,000건

### API 제한 사항
- JobKorea AJAX API: 250페이지 제한 (시간대별 가변)
- 페이지당 40건 → 최대 10,000건/요청
- **해결책**: 구(區)별 분할 크롤링

### 서울 25개 구 현황

| 구역 | 공고 수 | 수집 가능 | 비고 |
|-----|--------|---------|------|
| 강남구 | 16,039 | **16,039** | ✓ 분할 크롤링 |
| 기타 24개 구 | 66,815 | 66,815 | ✓ |
| **합계** | **82,854** | **82,854** | **100%** |

> **강남구 분할 전략**: jobtype + career 조합으로 8개 쿼리로 분할하여 전수 수집

```
강남구 분할 쿼리:
├── 정규직+신입: 2,410건 ✓
├── 정규직+경력: 6,692건 ✓
├── 정규직+경력무관: 3,294건 ✓
├── 계약직: 3,320건 ✓
├── 파견직: 419건 ✓
├── 위촉직: 45건 ✓
├── 인턴: 7건 ✓
└── 아르바이트: 64건 ✓
→ 중복 제거 후 16,039건 전수 수집
```

---

## 실행 계획

### Phase 1: 사전 점검 (5분)

```bash
# 1. 네트워크 상태 확인
ping -c 3 www.jobkorea.co.kr

# 2. 프록시 상태 확인 (IPRoyal)
curl -x http://user:pass@proxy.iproyal.com:12321 https://httpbin.org/ip

# 3. DB 연결 확인
cd crawler && source venv/bin/activate
python -c "from app.db.firestore import get_job_stats; import asyncio; print(asyncio.run(get_job_stats()))"

# 4. 현재 공고 수 확인
python -c "
import asyncio, httpx, re
async def check():
    async with httpx.AsyncClient() as c:
        r = await c.get('https://www.jobkorea.co.kr/Recruit/Home/_GI_List',
            params={'Page':1,'local':'I000'}, headers={'X-Requested-With':'XMLHttpRequest'})
        m = re.search(r'hdnGICnt.*?value=\"([\\d,]+)\"', r.text)
        print(f'서울 전체: {m.group(1)}건' if m else 'Failed')
asyncio.run(check())
"
```

### Phase 2: 목록 수집 (예상 40분)

```bash
# 구별 순차 크롤링 실행
cd /Users/stlee/Desktop/jobbot/jobai/crawler
source venv/bin/activate
python run_crawl_by_gu.py
```

**예상 과정:**
1. 25개 구 순차 처리
2. 각 구당 1-3분 (페이지 수에 따라)
3. 중복 ID 자동 제거
4. 총 ~77,000개 고유 ID 수집

**모니터링 포인트:**
- `[구이름] N건 (M페이지)` - 각 구 시작
- `페이지 50/250: 누적 N개` - 진행 상황
- `[진행] 전체 고유 ID: N개` - 누적 현황

### Phase 3: 상세 수집 (예상 2-3시간)

목록 수집 완료 후 자동 실행됨.

**설정:**
- Workers: 10개 (병렬 요청)
- Batch: 500건씩 DB 저장
- Proxy: 직접 연결 우선, 차단 시 프록시 전환

**예상 속도:**
- ~500건/분 (직접 연결)
- ~200건/분 (프록시 사용)

### Phase 4: 검증 (10분)

```bash
# 1. 최종 DB 상태 확인
python -c "
from app.db.firestore import get_job_stats
import asyncio
stats = asyncio.run(get_job_stats())
print(f'총 공고: {stats[\"total_jobs\"]:,}건')
"

# 2. 데이터 품질 샘플 확인
python test_e2e_quality.py

# 3. 백엔드 검색 테스트
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "백엔드 개발자 연봉 4000 이상"}'
```

---

## 예상 일정

| 단계 | 예상 시간 | 설명 |
|-----|---------|------|
| 사전 점검 | 5분 | 네트워크, DB 확인 |
| 목록 수집 | 40분 | 25개 구 순차 크롤링 |
| 상세 수집 | 2-3시간 | ~77,000건 상세 정보 |
| 검증 | 10분 | 데이터 품질 확인 |
| **총계** | **~3-4시간** | |

---

## 위험 요소 및 대응

### 1. IP 차단
**증상:** 429 Too Many Requests, 빈 응답, 캡차 페이지
**대응:**
- 자동 프록시 전환 (구현됨)
- 요청 속도 자동 조절 (구현됨)
- 수동 개입: 5-10분 대기 후 재시도

### 2. 네트워크 불안정
**증상:** Timeout, Connection reset
**대응:**
- 자동 재시도 (3회)
- 실패한 ID는 로그에 기록
- 수동 개입: 네트워크 확인 후 재실행

### 3. Firestore 쓰기 제한
**증상:** 429 Quota exceeded
**대응:**
- Batch 크기 축소 (500 → 200)
- 쓰기 간격 추가

### 4. 강남구 10,000건 초과 → 해결됨
**대응:** jobtype + career 조합으로 8개 쿼리 분할
**결과:** 100% 전수 수집 (16,039건)

---

## 중단/재개 방법

### 중단
```bash
# Ctrl+C로 중단
# 현재까지 수집된 데이터는 DB에 저장됨
```

### 재개
```bash
# 동일 명령어로 재실행
python run_crawl_by_gu.py

# 이미 수집된 공고는 updated로 처리 (중복 저장 없음)
```

---

## 크롤링 후 체크리스트

- [ ] DB 총 공고 수 확인 (목표: ~77,000건)
- [ ] 구별 분포 확인 (강남구 최다)
- [ ] 최신 공고 존재 확인 (오늘 날짜)
- [ ] 백엔드 검색 테스트
- [ ] 프론트엔드 UI 테스트

---

## 실행 명령어 (복사용)

```bash
# 전체 실행
cd /Users/stlee/Desktop/jobbot/jobai/crawler && \
source venv/bin/activate && \
python run_crawl_by_gu.py 2>&1 | tee crawl_$(date +%Y%m%d_%H%M%S).log
```

> 로그 파일로 저장하면서 실행. 중단 시에도 기록 보존.
