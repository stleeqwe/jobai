# GCP 설정 가이드

> **프로젝트**: jobbot-484505
> **최종 업데이트**: 2026-01-16

---

## 현재 상태

### 프로젝트 정보

| 항목 | 값 |
|------|-----|
| 프로젝트 ID | `jobbot-484505` |
| 프로젝트 번호 | `192887181758` |
| 리전 | `asia-northeast3` (서울) |
| 빌링 계정 | `01C9EE-C5748C-50BD6B` |
| 빌링 상태 | **활성화됨** |

### 활성화된 API

| API | 상태 | 용도 |
|-----|------|------|
| Cloud Run Admin API | ✅ 활성화 | 서비스 배포 |
| Artifact Registry API | ✅ 활성화 | Docker 이미지 저장 |
| Cloud Build API | ✅ 활성화 | 이미지 빌드 |
| Secret Manager API | ✅ 활성화 | 시크릿 관리 |
| Cloud Storage API | ✅ 활성화 | 스토리지 |
| Cloud Datastore API | ✅ 활성화 | Firestore |
| Cloud Logging API | ✅ 활성화 | 로깅 |
| Cloud Monitoring API | ✅ 활성화 | 모니터링 |

### Artifact Registry

| 항목 | 값 |
|------|-----|
| 저장소 이름 | `jobbot` |
| 위치 | `asia-northeast3` |
| 형식 | Docker |
| Registry URI | `asia-northeast3-docker.pkg.dev/jobbot-484505/jobbot` |

---

## 설정 명령어

### 1. gcloud 초기 설정

```bash
# 로그인
gcloud auth login

# 프로젝트 설정
gcloud config set project jobbot-484505

# 리전 설정
gcloud config set run/region asia-northeast3

# 설정 확인
gcloud config list
```

### 2. Docker 인증

```bash
# Artifact Registry 인증 설정
gcloud auth configure-docker asia-northeast3-docker.pkg.dev
```

### 3. API 활성화 (이미 완료)

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  --project=jobbot-484505
```

### 4. Artifact Registry 저장소 (이미 완료)

```bash
gcloud artifacts repositories create jobbot \
  --repository-format=docker \
  --location=asia-northeast3 \
  --description="JobBot Docker images" \
  --project=jobbot-484505
```

---

## 시크릿 관리

### 필수 시크릿 목록

| 시크릿 이름 | 용도 | 서비스 | 상태 |
|------------|------|--------|------|
| `gemini-api-key` | Gemini API 키 | backend | ❌ 미생성 |
| `firestore-key` | Firestore 서비스 계정 키 | backend, crawler | ❌ 미생성 |
| `proxy-credentials` | IPRoyal 프록시 인증 | crawler | ❌ 미생성 (선택) |

### 시크릿 생성 방법

```bash
# 텍스트 시크릿 생성
echo -n "YOUR_API_KEY" | gcloud secrets create gemini-api-key \
  --data-file=- \
  --project=jobbot-484505

# 파일 시크릿 생성 (서비스 계정 키)
gcloud secrets create firestore-key \
  --data-file=path/to/service-account.json \
  --project=jobbot-484505

# 시크릿 목록 확인
gcloud secrets list --project=jobbot-484505

# 시크릿 버전 확인
gcloud secrets versions list gemini-api-key --project=jobbot-484505
```

### 시크릿 업데이트

```bash
# 새 버전 추가
echo -n "NEW_API_KEY" | gcloud secrets versions add gemini-api-key --data-file=-

# 이전 버전 비활성화
gcloud secrets versions disable VERSION_ID --secret=gemini-api-key
```

---

## 배포 대상 서비스

### Cloud Run Services

| 서비스 | 설명 | 메모리 | CPU | 상태 |
|--------|------|--------|-----|------|
| `jobbot-backend` | FastAPI 백엔드 | 512Mi | 1 | ❌ 미배포 |
| `jobbot-frontend` | React 프론트엔드 | 256Mi | 1 | ❌ 미배포 |

### Cloud Run Jobs

| Job | 설명 | 메모리 | CPU | 상태 |
|-----|------|--------|-----|------|
| `jobbot-crawler` | 크롤러 스케줄 작업 | 2Gi | 2 | ❌ 미배포 |

---

## Docker 이미지 빌드 & 푸시

### Backend

```bash
cd backend

# 빌드
docker build -t asia-northeast3-docker.pkg.dev/jobbot-484505/jobbot/backend:latest .

# 푸시
docker push asia-northeast3-docker.pkg.dev/jobbot-484505/jobbot/backend:latest
```

### Frontend

```bash
cd frontend

# 빌드
docker build -t asia-northeast3-docker.pkg.dev/jobbot-484505/jobbot/frontend:latest .

# 푸시
docker push asia-northeast3-docker.pkg.dev/jobbot-484505/jobbot/frontend:latest
```

### Crawler

```bash
cd crawler

# 빌드
docker build -t asia-northeast3-docker.pkg.dev/jobbot-484505/jobbot/crawler:latest .

# 푸시
docker push asia-northeast3-docker.pkg.dev/jobbot-484505/jobbot/crawler:latest
```

---

## Cloud Run 배포

### Backend 배포

```bash
gcloud run deploy jobbot-backend \
  --image=asia-northeast3-docker.pkg.dev/jobbot-484505/jobbot/backend:latest \
  --region=asia-northeast3 \
  --platform=managed \
  --allow-unauthenticated \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=10 \
  --timeout=300 \
  --set-env-vars="ENVIRONMENT=production" \
  --set-secrets="GEMINI_API_KEY=gemini-api-key:latest" \
  --project=jobbot-484505
```

### Frontend 배포

```bash
gcloud run deploy jobbot-frontend \
  --image=asia-northeast3-docker.pkg.dev/jobbot-484505/jobbot/frontend:latest \
  --region=asia-northeast3 \
  --platform=managed \
  --allow-unauthenticated \
  --memory=256Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=5 \
  --project=jobbot-484505
```

### Crawler Job 배포

```bash
gcloud run jobs deploy jobbot-crawler \
  --image=asia-northeast3-docker.pkg.dev/jobbot-484505/jobbot/crawler:latest \
  --region=asia-northeast3 \
  --memory=2Gi \
  --cpu=2 \
  --task-timeout=3600 \
  --max-retries=1 \
  --set-env-vars="ENVIRONMENT=production" \
  --set-secrets="GOOGLE_APPLICATION_CREDENTIALS=/secrets/firestore-key:firestore-key:latest" \
  --project=jobbot-484505
```

---

## 상태 확인 명령어

### 서비스 목록

```bash
gcloud run services list --region=asia-northeast3 --project=jobbot-484505
```

### 서비스 상세

```bash
gcloud run services describe jobbot-backend --region=asia-northeast3 --project=jobbot-484505
```

### 리비전 목록

```bash
gcloud run revisions list --service=jobbot-backend --region=asia-northeast3 --project=jobbot-484505
```

### 로그 확인

```bash
# 실시간 로그
gcloud run services logs tail jobbot-backend --region=asia-northeast3 --project=jobbot-484505

# 최근 로그
gcloud run services logs read jobbot-backend --region=asia-northeast3 --limit=50 --project=jobbot-484505
```

### 이미지 목록

```bash
gcloud artifacts docker images list asia-northeast3-docker.pkg.dev/jobbot-484505/jobbot
```

---

## 롤백

```bash
# 이전 리비전으로 트래픽 전환
gcloud run services update-traffic jobbot-backend \
  --to-revisions=REVISION_NAME=100 \
  --region=asia-northeast3 \
  --project=jobbot-484505
```

---

## 비용 관리

### 예상 비용 (월간)

| 항목 | 예상 비용 | 비고 |
|------|----------|------|
| Cloud Run | $0-10 | 트래픽 기반 |
| Artifact Registry | $0-5 | 이미지 저장 |
| Secret Manager | $0.06/시크릿 | 월 3개 |
| Cloud Build | 무료 | 120분/일 무료 |

### 비용 절감 팁

1. **min-instances=0**: 트래픽 없을 때 인스턴스 0개
2. **Cloud Build 사용**: `--source .` 옵션으로 무료 빌드
3. **이미지 정리**: 오래된 이미지 주기적 삭제

```bash
# 30일 이상 된 이미지 삭제
gcloud artifacts docker images list asia-northeast3-docker.pkg.dev/jobbot-484505/jobbot \
  --include-tags --filter="createTime < -P30D" --format="get(package)"
```

---

## 트러블슈팅

### API 미활성화 오류

```
ERROR: API [run.googleapis.com] not enabled on project
```

**해결:**
```bash
gcloud services enable run.googleapis.com --project=jobbot-484505
```

### 권한 오류

```
ERROR: does not have permission to access
```

**해결:**
```bash
# 현재 계정 확인
gcloud auth list

# 다른 계정으로 전환
gcloud config set account YOUR_EMAIL@gmail.com
```

### 이미지 푸시 실패

```
denied: Permission denied
```

**해결:**
```bash
# Docker 인증 설정
gcloud auth configure-docker asia-northeast3-docker.pkg.dev
```

---

## 다음 단계

배포 전 완료해야 할 항목:

- [ ] `gemini-api-key` 시크릿 생성
- [ ] `firestore-key` 시크릿 생성 (서비스 계정 키)
- [ ] Dockerfile 확인 (backend, frontend, crawler)
- [ ] 로컬 테스트 완료
- [ ] 배포 스크립트 실행
