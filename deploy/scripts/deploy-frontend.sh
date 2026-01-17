#!/bin/bash
# JobBot Frontend 배포 스크립트
# Cloud Run Service로 배포 (nginx)

set -e

# 공통 설정 로드
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/config.sh"

# 서비스 설정
SERVICE_NAME="$FRONTEND_SERVICE"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}JobBot Frontend 배포${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "서비스: $SERVICE_NAME"
echo "리전: $REGION"
echo "프로젝트: $PROJECT_ID"
echo ""

# 현재 리비전 기록 (롤백용)
echo -e "${YELLOW}[1/4] 현재 리비전 기록...${NC}"
CURRENT_REVISION=$(gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --format='value(status.latestReadyRevisionName)' 2>/dev/null || echo "none")
echo "현재 리비전: $CURRENT_REVISION"

# 백엔드 URL 확인
echo -e "${YELLOW}[2/4] 백엔드 URL 확인...${NC}"
BACKEND_URL=$(gcloud run services describe jobbot-backend \
    --region=$REGION \
    --format='value(status.url)' 2>/dev/null || echo "")

if [ -z "$BACKEND_URL" ]; then
    echo -e "${RED}Warning: 백엔드 서비스 URL을 찾을 수 없습니다.${NC}"
    echo "VITE_API_URL 환경변수를 수동으로 설정해야 합니다."
else
    echo "백엔드 URL: $BACKEND_URL"
fi

# 배포
echo -e "${YELLOW}[3/4] 배포 시작...${NC}"
cd "$(dirname "$0")/../../frontend"

# .env.production 생성 (빌드 시 사용)
if [ -n "$BACKEND_URL" ]; then
    echo "VITE_API_URL=$BACKEND_URL" > .env.production
    echo ".env.production 생성 완료"
fi

gcloud run deploy $SERVICE_NAME \
    --source . \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --memory 256Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 5 \
    --project $PROJECT_ID

# 서비스 URL 확인
echo -e "${YELLOW}[4/4] 서비스 URL 확인...${NC}"
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --format='value(status.url)')
echo "서비스 URL: $SERVICE_URL"

# 헬스체크
sleep 3
HEALTH_RESPONSE=$(curl -s "$SERVICE_URL/health" || echo '{"error": "failed"}')
echo "헬스체크 응답: $HEALTH_RESPONSE"

if echo "$HEALTH_RESPONSE" | grep -q 'healthy'; then
    echo -e "${GREEN}✓ 배포 성공!${NC}"

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
    echo "  ./rollback.sh frontend $CURRENT_REVISION"
else
    echo -e "${RED}✗ 헬스체크 실패${NC}"
    echo "롤백을 고려하세요: ./rollback.sh frontend $CURRENT_REVISION"
    exit 1
fi
