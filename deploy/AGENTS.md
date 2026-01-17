# Deploy Agent Instructions

> **목적**: GCP Cloud Run 배포 작업의 안전한 실행 및 변경 이력 관리
> **최종 업데이트**: 2026-01-16
> **GCP 설정**: [GCP_SETUP.md](./GCP_SETUP.md) 참조

---

## 🔀 작업 요청 경로

Codex는 **두 가지 경로**로 배포 작업 요청을 받습니다:

| 경로 | 트리거 | 특징 |
|------|--------|------|
| **A. 직접 요청** | 사용자가 Codex 직접 호출 | 독립 작업, Step 1~7 절차 |
| **B. 협업 요청** | Claude가 계획 수립 후 위임 | Claude 계획 검토 + 실행 |

### 경로 판단

```
요청 수신 → "[Codex 배포 요청]" 형식인가?
              │
         Yes  │  No
              ↓   ↓
         경로 B   경로 A
        (협업)   (직접)
```

---

## 🅰️ 경로 A: 직접 요청 (사용자 → Codex)

사용자가 직접 Codex를 호출한 경우, **Step 1~7 절차**를 따릅니다.

→ 아래 "절대 규칙" 섹션 참조

---

## 🅱️ 경로 B: Claude-Codex 협업

Claude가 배포 계획을 수립하고 실행을 위임합니다.

### 역할 분담

| 역할 | Claude | Codex (나) |
|------|--------|------------|
| 배포 전략 분석 | ✓ | |
| 인프라 계획 수립 | ✓ | |
| 리스크 평가 | ✓ | |
| **계획 검토 및 검증** | | ✓ |
| **Dockerfile 작성/수정** | | ✓ |
| **Cloud Run 설정** | | ✓ |
| **gcloud 명령 실행** | | ✓ |
| **이슈 기록** | | ✓ |
| **배포 검증** | | ✓ |

### 협업 요청 수신 시 워크플로우

Claude로부터 `[Codex 배포 요청]`을 수신하면:

```
1. Claude 계획 검토
   - 배포 전략이 적절한지 확인
   - 누락된 설정 있는지 확인
   - 보안 이슈 없는지 확인

2. 사전 체크리스트
   - [ ] 시크릿이 코드에 노출되지 않는가?
   - [ ] 환경변수 설정이 완전한가?
   - [ ] 롤백 계획이 있는가?

3. 이슈 생성 (Step 3)
   - 배포 내용 문서화

4. 실행 + 검증
   - gcloud 명령 실행
   - 헬스체크 확인
   - 로그 확인

5. 결과 공유
   - 배포 URL
   - 성공/실패 상태
```

### 협업 요청 형식 (수신)

```
[Codex 배포 요청]

## 1. 배포 대상
- 서비스: backend / frontend / crawler
- 환경: dev / staging / prod

## 2. Claude 계획
- 배포 전략: (신규 배포 / 업데이트 / 롤백)
- 변경 사항: (요약)
- 예상 다운타임: (없음 / 있음)

## 3. 실행 항목
- [ ] Dockerfile 확인/수정
- [ ] Cloud Run 서비스 설정
- [ ] 환경변수 설정
- [ ] 배포 실행
- [ ] 헬스체크 확인

## 4. 환경변수 (시크릿 제외)
- ENVIRONMENT=production
- ...

## 5. 주의사항
- (있다면 기술)

## 6. 롤백 계획
- (이전 리비전으로 롤백 방법)
```

### 협업 응답 형식 (발신)

```
[Codex 배포 결과]

## 1. 실행 결과
- 상태: 성공 / 실패
- 서비스 URL: https://xxx.run.app
- 리비전: xxx-00001-abc

## 2. 검증 결과
- 헬스체크: OK / FAIL
- 응답 시간: Xms

## 3. 변경 이력
- 이슈 번호: #NNN
- 이전 리비전: xxx-00000-xyz

## 4. 문제점 (있다면)
- (기술)

## 5. 다음 단계
- [ ] 프로덕션 모니터링 확인
```

---

## 🚨 절대 규칙: 배포 전 이슈 먼저

**어떤 배포 작업이든 아래 순서를 반드시 따를 것.**

```
배포 요청 수신 → [Step 1~2] 사전 체크 & 기존 이슈 조회 → [Step 3] 이슈 생성
              → [Step 4] 배포 계획 기록 → [Step 5] 배포 실행
              → [Step 6] 검증 → [Step 7] 이슈 닫기
```

---

## Step 1: 사전 체크

### 보안 체크리스트 (필수!)

```bash
# 시크릿 노출 확인
grep -rn "GEMINI_API_KEY\|password\|secret" deploy/ --include="*.yaml" --include="*.sh"

# .env 파일이 gitignore에 있는지 확인
cat .gitignore | grep -E "\.env"
```

**확인 사항:**
- [ ] API 키가 코드/설정에 하드코딩 되어있지 않은가?
- [ ] 시크릿은 Secret Manager 사용하는가?
- [ ] .env 파일이 커밋되지 않는가?

### 현재 상태 확인

```bash
# 현재 배포된 서비스 확인
gcloud run services list --region=asia-northeast3

# 현재 리비전 확인
gcloud run revisions list --service=SERVICE_NAME --region=asia-northeast3
```

---

## Step 2: 기존 이슈 조회 (필수!)

```bash
# 이슈 목록 확인
ls -la .codex/issues/

# 키워드로 검색
grep -ri "cloud run\|배포\|deploy" .codex/issues/

# 최근 배포 이슈 확인
grep -ri "backend\|frontend" .codex/issues/
```

**확인 사항:**
- [ ] 이전 배포에서 문제가 있었는가?
- [ ] 동일한 서비스 배포 이력이 있는가?
- [ ] 롤백 경험이 있는가?

---

## Step 3: 새 이슈 생성

```bash
# 다음 이슈 번호 확인
ls .codex/issues/ | grep -E "^[0-9]+" | sort -n | tail -1

# 새 이슈 파일 생성
cp .codex/issues/_TEMPLATE.md .codex/issues/NNN_deploy_서비스명.md
```

**파일명 규칙**: `NNN_deploy_서비스_환경.md`
- 예: `001_deploy_backend_prod.md`
- 예: `002_deploy_frontend_staging.md`

---

## Step 4: 배포 계획 기록

**이슈 파일에 배포 계획 작성:**

```markdown
## 5. 배포 계획

### 대상
- 서비스: backend
- 환경: production
- 리전: asia-northeast3

### 변경 사항
- (변경 내용)

### 실행 명령어
```bash
gcloud run deploy SERVICE_NAME \
  --source . \
  --region asia-northeast3 \
  --platform managed
```

### 환경변수
- ENVIRONMENT=production
- (시크릿은 Secret Manager 참조)

### 롤백 계획
```bash
gcloud run services update-traffic SERVICE_NAME \
  --to-revisions=PREVIOUS_REVISION=100 \
  --region=asia-northeast3
```
```

---

## Step 5: 배포 실행

### Backend (FastAPI)

```bash
cd backend

# 빌드 + 배포
gcloud run deploy jobbot-backend \
  --source . \
  --region asia-northeast3 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "ENVIRONMENT=production" \
  --set-secrets "GEMINI_API_KEY=gemini-api-key:latest"
```

### Frontend (React/Vite)

```bash
cd frontend

# 빌드
npm run build

# 배포 (Cloud Run with nginx)
gcloud run deploy jobbot-frontend \
  --source . \
  --region asia-northeast3 \
  --platform managed \
  --allow-unauthenticated
```

### Crawler (스케줄 작업)

```bash
cd crawler

# Cloud Run Jobs로 배포
gcloud run jobs deploy jobbot-crawler \
  --source . \
  --region asia-northeast3 \
  --set-env-vars "ENVIRONMENT=production" \
  --set-secrets "GOOGLE_APPLICATION_CREDENTIALS=firestore-key:latest"
```

---

## Step 6: 검증 (필수!)

```bash
# 서비스 URL 확인
gcloud run services describe SERVICE_NAME --region=asia-northeast3 --format="value(status.url)"

# 헬스체크
curl -s https://SERVICE_URL/health | jq

# 로그 확인
gcloud run services logs read SERVICE_NAME --region=asia-northeast3 --limit=50
```

**이슈 파일에 결과 기록:**

```markdown
## 6. 검증

### 결과
| 항목 | 결과 |
|------|------|
| 배포 상태 | 성공 |
| 서비스 URL | https://xxx.run.app |
| 헬스체크 | OK |
| 리비전 | xxx-00001-abc |

### 응답 확인
```json
{"status": "healthy", "version": "1.0.0"}
```
```

---

## Step 7: 이슈 닫기

```markdown
**상태**: `resolved`
**배포일**: 2026-01-16
**리비전**: xxx-00001-abc
```

---

## 🚫 금지 사항

1. **이슈 파일 없이 배포 금지**
2. **시크릿 하드코딩 금지** → Secret Manager 사용
3. **프로덕션 직접 배포 금지** → staging 먼저 검증
4. **검증 없이 완료 처리 금지**
5. **롤백 계획 없이 배포 금지**

---

## 📁 디렉토리 구조

```
deploy/
├── AGENTS.md                 # 이 파일 (Codex 자동 로드)
├── GCP_SETUP.md              # GCP 설정 및 현재 상태 문서
├── .codex/
│   └── issues/               # 배포 이슈 기록
│       ├── _TEMPLATE.md
│       └── NNN_deploy_*.md
├── docker/
│   ├── backend.Dockerfile
│   ├── frontend.Dockerfile
│   └── crawler.Dockerfile
├── infra/
│   ├── cloud-run-backend.yaml
│   ├── cloud-run-frontend.yaml
│   └── cloud-run-jobs.yaml
└── scripts/
    ├── config.sh             # 공통 설정 (프로젝트 ID, 리전 등)
    ├── deploy-backend.sh
    ├── deploy-frontend.sh
    ├── deploy-crawler.sh
    └── rollback.sh
```

## ☁️ GCP 프로젝트 정보

> 상세: [GCP_SETUP.md](./GCP_SETUP.md)

| 항목 | 값 |
|------|-----|
| 프로젝트 ID | `jobbot-484505` |
| 리전 | `asia-northeast3` (서울) |
| Artifact Registry | `asia-northeast3-docker.pkg.dev/jobbot-484505/jobbot` |
| 빌링 상태 | 활성화됨 |

### 활성화된 API

- Cloud Run Admin API
- Artifact Registry API
- Cloud Build API
- Secret Manager API

---

## 🔧 유용한 명령어

### 서비스 관리

```bash
# 서비스 목록
gcloud run services list --region=asia-northeast3

# 서비스 상세
gcloud run services describe SERVICE_NAME --region=asia-northeast3

# 트래픽 분배 (카나리 배포)
gcloud run services update-traffic SERVICE_NAME \
  --to-revisions=NEW_REV=10,OLD_REV=90 \
  --region=asia-northeast3
```

### 롤백

```bash
# 이전 리비전으로 100% 트래픽
gcloud run services update-traffic SERVICE_NAME \
  --to-revisions=PREVIOUS_REVISION=100 \
  --region=asia-northeast3
```

### 로그

```bash
# 실시간 로그
gcloud run services logs tail SERVICE_NAME --region=asia-northeast3

# 에러 로그만
gcloud logging read "resource.type=cloud_run_revision AND severity>=ERROR" --limit=50
```

---

## 🔐 시크릿 관리

### Secret Manager 사용

```bash
# 시크릿 생성
echo -n "your-api-key" | gcloud secrets create SECRET_NAME --data-file=-

# 시크릿 버전 추가
echo -n "new-api-key" | gcloud secrets versions add SECRET_NAME --data-file=-

# Cloud Run에서 시크릿 사용
gcloud run deploy SERVICE_NAME \
  --set-secrets "ENV_VAR=SECRET_NAME:latest"
```

### 필수 시크릿 목록

| 시크릿 이름 | 용도 | 서비스 |
|------------|------|--------|
| `gemini-api-key` | Gemini API | backend |
| `firestore-key` | Firestore 인증 | backend, crawler |
| `proxy-credentials` | IPRoyal 프록시 | crawler |

---

## 📋 배포 체크리스트

### 배포 전

- [ ] 로컬 테스트 통과
- [ ] 시크릿 노출 확인
- [ ] 이슈 파일 생성
- [ ] 롤백 계획 준비

### 배포 중

- [ ] gcloud 명령 실행
- [ ] 빌드 로그 확인
- [ ] 배포 완료 대기

### 배포 후

- [ ] 헬스체크 확인
- [ ] 기능 테스트
- [ ] 로그 모니터링
- [ ] 이슈 파일 업데이트
