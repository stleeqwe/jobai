#!/bin/bash
# JobBot Backend 배포 스크립트
# Cloud Run Service로 배포

set -e

# 공통 설정 로드
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/config.sh"

# 서비스 설정
SERVICE_NAME="$BACKEND_SERVICE"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}JobBot Backend 배포${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "서비스: $SERVICE_NAME"
echo "리전: $REGION"
echo "프로젝트: $PROJECT_ID"
echo ""

# 사전 체크
echo -e "${YELLOW}[1/5] 사전 체크...${NC}"

# 시크릿 존재 확인
if ! gcloud secrets describe gemini-api-key --project="$PROJECT_ID" &>/dev/null; then
    echo -e "${RED}Error: gemini-api-key 시크릿이 없습니다.${NC}"
    echo "생성: echo -n 'YOUR_API_KEY' | gcloud secrets create gemini-api-key --data-file=-"
    exit 1
fi

if ! gcloud secrets describe firestore-key --project="$PROJECT_ID" &>/dev/null; then
    echo -e "${RED}Error: firestore-key 시크릿이 없습니다.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ 시크릿 확인 완료${NC}"

# 현재 리비전 기록 (롤백용)
echo -e "${YELLOW}[2/5] 현재 리비전 기록...${NC}"
CURRENT_REVISION=$(gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --format='value(status.latestReadyRevisionName)' 2>/dev/null || echo "none")
echo "현재 리비전: $CURRENT_REVISION"

# 배포
echo -e "${YELLOW}[3/5] 배포 시작...${NC}"
cd "$(dirname "$0")/../../backend"

gcloud run deploy $SERVICE_NAME \
    --source . \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 10 \
    --timeout 300 \
    --set-env-vars "ENVIRONMENT=production" \
    --set-secrets "GEMINI_API_KEY=gemini-api-key:latest" \
    --set-secrets "GOOGLE_APPLICATION_CREDENTIALS=/secrets/firestore-key:firestore-key:latest" \
    --project $PROJECT_ID

# 서비스 URL 확인
echo -e "${YELLOW}[4/5] 서비스 URL 확인...${NC}"
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --format='value(status.url)')
echo "서비스 URL: $SERVICE_URL"

# 헬스체크
echo -e "${YELLOW}[5/5] 헬스체크...${NC}"
sleep 5
HEALTH_RESPONSE=$(curl -s "$SERVICE_URL/health" || echo '{"error": "failed"}')
echo "응답: $HEALTH_RESPONSE"

if echo "$HEALTH_RESPONSE" | grep -q '"status"'; then
    echo -e "${GREEN}✓ 배포 성공!${NC}"

    # 새 리비전
    NEW_REVISION=$(gcloud run services describe $SERVICE_NAME \
        --region=$REGION \
        --format='value(status.latestReadyRevisionName)')
    echo ""
    echo "=========================================="
    echo "배포 완료"
    echo "=========================================="
    echo "이전 리비전: $CURRENT_REVISION"
    echo "새 리비전: $NEW_REVISION"
    echo "서비스 URL: $SERVICE_URL"
    echo ""
    echo "롤백 명령어:"
    echo "  ./rollback.sh backend $CURRENT_REVISION"
else
    echo -e "${RED}✗ 헬스체크 실패${NC}"
    echo "롤백을 고려하세요: ./rollback.sh backend $CURRENT_REVISION"
    exit 1
fi
