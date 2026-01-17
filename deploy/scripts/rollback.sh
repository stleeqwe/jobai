#!/bin/bash
# JobBot 롤백 스크립트
# Cloud Run Service 트래픽을 이전 리비전으로 전환

set -e

# 공통 설정 로드
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/config.sh"

# 사용법
usage() {
    echo "사용법: $0 <service> [revision]"
    echo ""
    echo "서비스:"
    echo "  backend   - jobbot-backend"
    echo "  frontend  - jobbot-frontend"
    echo ""
    echo "예시:"
    echo "  $0 backend                          # 이전 리비전 목록 표시"
    echo "  $0 backend jobbot-backend-00001    # 특정 리비전으로 롤백"
    echo ""
    exit 1
}

# 인자 체크
if [ -z "$1" ]; then
    usage
fi

# 서비스 이름 매핑
case "$1" in
    backend)
        SERVICE_NAME="jobbot-backend"
        ;;
    frontend)
        SERVICE_NAME="jobbot-frontend"
        ;;
    *)
        echo -e "${RED}Error: 알 수 없는 서비스 '$1'${NC}"
        usage
        ;;
esac

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}JobBot 롤백${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "서비스: $SERVICE_NAME"
echo "리전: $REGION"
echo ""

# 현재 리비전 확인
echo -e "${YELLOW}현재 리비전:${NC}"
CURRENT_REVISION=$(gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --format='value(status.latestReadyRevisionName)' \
    --project=$PROJECT_ID)
echo "  $CURRENT_REVISION (active)"
echo ""

# 리비전 목록 표시
echo -e "${YELLOW}사용 가능한 리비전:${NC}"
gcloud run revisions list \
    --service=$SERVICE_NAME \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format='table(name, status.conditions[0].status, createTime.date(), spec.containers[0].resources.limits.memory)'
echo ""

# 특정 리비전으로 롤백
if [ -n "$2" ]; then
    TARGET_REVISION="$2"

    # 리비전 존재 확인
    if ! gcloud run revisions describe $TARGET_REVISION \
        --region=$REGION \
        --project=$PROJECT_ID &>/dev/null; then
        echo -e "${RED}Error: 리비전 '$TARGET_REVISION'을 찾을 수 없습니다.${NC}"
        exit 1
    fi

    echo -e "${YELLOW}롤백 대상: $TARGET_REVISION${NC}"
    read -p "이 리비전으로 롤백하시겠습니까? (y/N): " CONFIRM

    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        echo "롤백 취소됨"
        exit 0
    fi

    echo ""
    echo "롤백 진행 중..."

    gcloud run services update-traffic $SERVICE_NAME \
        --to-revisions=$TARGET_REVISION=100 \
        --region=$REGION \
        --project=$PROJECT_ID

    echo ""
    echo -e "${GREEN}✓ 롤백 완료${NC}"
    echo ""
    echo "이전 리비전: $CURRENT_REVISION"
    echo "현재 리비전: $TARGET_REVISION"

    # 헬스체크
    SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
        --region=$REGION \
        --format='value(status.url)' \
        --project=$PROJECT_ID)

    echo ""
    echo "헬스체크 중..."
    sleep 3

    HEALTH_RESPONSE=$(curl -s "$SERVICE_URL/health" || echo '{"error": "failed"}')
    echo "응답: $HEALTH_RESPONSE"

    if echo "$HEALTH_RESPONSE" | grep -q 'healthy\|status'; then
        echo -e "${GREEN}✓ 서비스 정상${NC}"
    else
        echo -e "${RED}✗ 헬스체크 실패 - 서비스 상태를 확인하세요${NC}"
    fi
else
    echo "롤백하려면 리비전 이름을 지정하세요:"
    echo "  $0 $1 <revision-name>"
fi
