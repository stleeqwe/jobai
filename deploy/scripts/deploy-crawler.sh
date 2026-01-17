#!/bin/bash
# JobBot Crawler 배포 스크립트
# Cloud Run Jobs로 배포

set -e

# 공통 설정 로드
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/config.sh"

# Job 설정
JOB_NAME="$CRAWLER_JOB"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}JobBot Crawler 배포 (Cloud Run Jobs)${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Job: $JOB_NAME"
echo "리전: $REGION"
echo "프로젝트: $PROJECT_ID"
echo ""

# 사전 체크
echo -e "${YELLOW}[1/4] 사전 체크...${NC}"

# 시크릿 존재 확인
if ! gcloud secrets describe firestore-key --project="$PROJECT_ID" &>/dev/null; then
    echo -e "${RED}Error: firestore-key 시크릿이 없습니다.${NC}"
    exit 1
fi

# 프록시 시크릿 확인 (선택)
HAS_PROXY=false
if gcloud secrets describe proxy-credentials --project="$PROJECT_ID" &>/dev/null; then
    HAS_PROXY=true
    echo -e "${GREEN}✓ proxy-credentials 시크릿 존재${NC}"
else
    echo -e "${YELLOW}! proxy-credentials 시크릿 없음 (프록시 없이 실행)${NC}"
fi

echo -e "${GREEN}✓ 시크릿 확인 완료${NC}"

# 배포
echo -e "${YELLOW}[2/4] Job 배포 시작...${NC}"
cd "$(dirname "$0")/../../crawler"

# 기본 명령어
DEPLOY_CMD="gcloud run jobs deploy $JOB_NAME \
    --source . \
    --region $REGION \
    --memory 2Gi \
    --cpu 2 \
    --task-timeout 3600 \
    --max-retries 1 \
    --set-env-vars ENVIRONMENT=production \
    --set-secrets GOOGLE_APPLICATION_CREDENTIALS=/secrets/firestore-key:firestore-key:latest \
    --project $PROJECT_ID"

# 프록시 시크릿 추가
if [ "$HAS_PROXY" = true ]; then
    DEPLOY_CMD="$DEPLOY_CMD \
    --set-secrets PROXY_HOST=proxy-credentials:latest \
    --set-secrets PROXY_PORT=proxy-credentials:latest \
    --set-secrets PROXY_USERNAME=proxy-credentials:latest \
    --set-secrets PROXY_PASSWORD=proxy-credentials:latest"
fi

eval $DEPLOY_CMD

echo -e "${GREEN}✓ Job 배포 완료${NC}"

# 스케줄러 설정 안내
echo -e "${YELLOW}[3/4] 스케줄러 설정 안내...${NC}"
echo ""
echo "일일 크롤링 스케줄러 설정 (Cloud Scheduler):"
echo ""
echo "gcloud scheduler jobs create http ${JOB_NAME}-daily \\"
echo "  --location=$REGION \\"
echo "  --schedule='0 2 * * *' \\"
echo "  --time-zone='Asia/Seoul' \\"
echo "  --uri='https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run' \\"
echo "  --http-method=POST \\"
echo "  --oauth-service-account-email=\${SERVICE_ACCOUNT_EMAIL}"
echo ""

# 수동 실행 안내
echo -e "${YELLOW}[4/4] 수동 실행...${NC}"
echo ""
echo "수동 실행 명령어:"
echo "  gcloud run jobs execute $JOB_NAME --region=$REGION"
echo ""
echo "실행 로그 확인:"
echo "  gcloud run jobs executions list --job=$JOB_NAME --region=$REGION"
echo "  gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=$JOB_NAME' --limit=100"
echo ""

# 즉시 실행 옵션
read -p "지금 바로 Job을 실행하시겠습니까? (y/N): " EXECUTE_NOW
if [[ "$EXECUTE_NOW" =~ ^[Yy]$ ]]; then
    echo "Job 실행 중..."
    gcloud run jobs execute $JOB_NAME --region=$REGION --project=$PROJECT_ID
    echo -e "${GREEN}✓ Job 실행 시작됨${NC}"
    echo ""
    echo "실행 상태 확인:"
    echo "  gcloud run jobs executions list --job=$JOB_NAME --region=$REGION"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}배포 완료${NC}"
echo -e "${GREEN}========================================${NC}"
