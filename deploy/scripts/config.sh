#!/bin/bash
# JobBot 배포 공통 설정
# 최종 업데이트: 2026-01-16

# GCP 프로젝트 설정
export PROJECT_ID="jobbot-484505"
export REGION="asia-northeast3"

# Artifact Registry
export REGISTRY="asia-northeast3-docker.pkg.dev"
export REPOSITORY="jobbot"
export IMAGE_BASE="${REGISTRY}/${PROJECT_ID}/${REPOSITORY}"

# Cloud Run 서비스 이름
export BACKEND_SERVICE="jobbot-backend"
export FRONTEND_SERVICE="jobbot-frontend"
export CRAWLER_JOB="jobbot-crawler"

# 색상 (터미널 출력용)
export RED='\033[0;31m'
export GREEN='\033[0;32m'
export YELLOW='\033[1;33m'
export NC='\033[0m'

# 현재 설정 출력
print_config() {
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}JobBot 배포 설정${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "프로젝트: $PROJECT_ID"
    echo "리전: $REGION"
    echo "이미지 저장소: $IMAGE_BASE"
    echo ""
}
