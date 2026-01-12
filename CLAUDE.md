# JobChat 프로젝트 작업 가이드

## 프로젝트 개요
- **서비스**: 자연어 기반 채용공고 검색 (JobChat)
- **기술 스택**: React + FastAPI + Gemini 2.5 Flash-Lite + Firestore
- **GCP 프로젝트**: `jobchat-1768149763`
- **크롤링 대상**: 잡코리아 (강남구)

---

## 중요 교훈 및 주의사항

### 1. 크롤링 데이터 저장 - 반드시 중간 저장 필수
**사고 사례**: 15,000건 크롤링 후 프로세스 종료 시 데이터 전량 손실

**원인**: 크롤링 완료 후 한번에 저장하는 구조였음

**해결책**: 500건마다 중간 저장 (`save_callback` + `save_batch_size`)
```python
jobs, result = await scraper.crawl_all_parallel(
    save_callback=save_jobs,
    save_batch_size=500  # 500건마다 DB 저장
)
```

**교훈**:
- 장시간 작업은 반드시 중간 저장 구조로 설계
- 프로세스 종료 전 저장 여부 확인 필수

---

### 2. 상세 페이지 파싱 - 정규식 패턴 주의

#### 급여 파싱
- 범위 패턴 우선: `월급 230~270만원`
- "면접", "협의" 등 키워드 있으면 negotiable 처리됨
- 월급 → 연봉 자동 환산 (x12)

```python
salary_patterns = [
    r'(월급?\s*[\d,]+\s*~\s*[\d,]+\s*만원)',  # 범위 우선
    r'(연봉?\s*[\d,]+\s*만원)',
    # ...
]
```

#### 주소 파싱
- 닫히지 않은 괄호 제거 필요
- 길이 제한 (10~60자)

---

### 3. Firestore 저장 필드 구조

```
기본 정보:
- id, title, url, source
- company_name

직무 정보:
- job_type (정규화된 직무명)
- job_type_raw (원본)
- job_category (대분류)
- job_keywords (키워드 배열)
- job_description (업무내용, 최대 500자)

위치 정보:
- location_sido, location_gugun, location_full
- location_dong
- company_address (상세 주소)

급여 정보:
- salary_text (원본)
- salary_min, salary_max (만원 단위, 연봉 환산)
- salary_type (annual/monthly/hourly/negotiable)

채용 조건:
- experience_type (신입/경력/무관)
- experience_min, experience_max
- education
- employment_type (정규직/계약직 등)

기업 정보:
- company_size (중소기업/대기업/스타트업 등)
- benefits (복리후생 키워드 배열)
- industry

마감 정보:
- deadline, deadline_type, deadline_date
- is_active

메타:
- created_at, updated_at, last_verified
- view_count
```

---

### 4. 크롤러 실행 명령어

```bash
# 전체 크롤링 (5워커, 500건마다 저장)
cd /Users/iseungtae/Desktop/jobai/crawler
source venv/bin/activate
PYTHONUNBUFFERED=1 python3 -m app.main --mode full --workers 5

# 테스트 크롤링 (특정 페이지 수)
python3 -c "
import asyncio
from app.scrapers import JobKoreaScraper
from app.db import save_jobs

async def run():
    scraper = JobKoreaScraper(num_workers=5)
    jobs, result = await scraper.crawl_all_parallel(
        max_pages=100,
        save_callback=save_jobs,
        save_batch_size=500
    )
    await scraper.close()

asyncio.run(run())
"
```

---

### 5. 서버 실행

```bash
# Backend (포트 8000)
cd /Users/iseungtae/Desktop/jobai/backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Frontend (포트 5173 또는 5174)
cd /Users/iseungtae/Desktop/jobai/frontend
npm run dev
```

---

### 6. 환경 변수

```
# crawler/.env
GOOGLE_CLOUD_PROJECT=jobchat-1768149763
GOOGLE_APPLICATION_CREDENTIALS=/Users/iseungtae/jobchat-credentials.json

# backend/.env
GEMINI_API_KEY=...
```

---

### 7. 크롤링 속도 관련

- 상세 페이지 요청이 가장 큰 병목 (공고당 0.3~0.6초 추가)
- 워커 5개 = 분당 약 50페이지, 150건
- 5,000건 수집 예상 시간: 약 30~40분

---

### 8. 주의사항 체크리스트

- [ ] 크롤링 전 중간 저장 설정 확인
- [ ] 프로세스 종료 전 저장 완료 확인
- [ ] 새 필드 추가 시 return 문에도 추가
- [ ] 정규식 테스트 후 적용
- [ ] 장시간 작업은 백그라운드로 실행
- [ ] 크롤링 모니터링 (tail -f)

---

## 파일 구조

```
jobai/
├── crawler/
│   ├── app/
│   │   ├── main.py          # 크롤러 실행
│   │   ├── scrapers/
│   │   │   └── jobkorea.py  # 잡코리아 크롤러
│   │   ├── normalizers/     # 데이터 정규화
│   │   └── db/
│   │       └── firestore.py # DB 저장
│   └── venv/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI 서버
│   │   ├── routers/
│   │   └── services/
│   └── venv/
├── frontend/
│   └── src/
│       ├── components/
│       └── hooks/
└── CLAUDE.md                # 이 파일
```

---

## 다음 작업

1. Backend API 완성
   - Gemini Function Calling 연동
   - 검색 쿼리 최적화

2. Frontend 완성
   - 채팅 UI
   - 공고 카드 렌더링

3. 배포
   - Cloud Run (Backend)
   - Firebase Hosting (Frontend)
   - Cloud Scheduler (크롤링 자동화)
