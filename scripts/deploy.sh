#!/bin/bash

# JobChat 배포 스크립트
# 사용법: ./scripts/deploy.sh [backend|frontend|crawler|all]

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 프로젝트 루트
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 설정 로드
if [ -f "$PROJECT_ROOT/.env" ]; then
    source "$PROJECT_ROOT/.env"
fi

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-jobchat-project}"
REGION="${REGION:-asia-northeast3}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}JobChat 배포 스크립트${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "프로젝트: ${YELLOW}${PROJECT_ID}${NC}"
echo -e "리전: ${YELLOW}${REGION}${NC}"
echo ""

deploy_backend() {
    echo -e "${YELLOW}[Backend] Cloud Run 배포 시작...${NC}"
    cd "$PROJECT_ROOT/backend"

    # Secret Manager에 API 키 저장 (최초 1회)
    if ! gcloud secrets describe gemini-api-key --project=$PROJECT_ID > /dev/null 2>&1; then
        echo -e "${YELLOW}Gemini API 키를 Secret Manager에 저장합니다...${NC}"
        echo -n "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key \
            --data-file=- \
            --project=$PROJECT_ID
    fi

    # Cloud Run 배포
    gcloud run deploy jobchat-api \
        --source . \
        --region $REGION \
        --platform managed \
        --allow-unauthenticated \
        --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT_ID,ENVIRONMENT=production" \
        --set-secrets "GEMINI_API_KEY=gemini-api-key:latest" \
        --memory 512Mi \
        --cpu 1 \
        --min-instances 0 \
        --max-instances 10 \
        --timeout 60 \
        --project $PROJECT_ID

    # 배포된 URL 가져오기
    BACKEND_URL=$(gcloud run services describe jobchat-api \
        --region $REGION \
        --project $PROJECT_ID \
        --format 'value(status.url)')

    echo -e "${GREEN}[Backend] 배포 완료: ${BACKEND_URL}${NC}"
    echo "$BACKEND_URL" > "$PROJECT_ROOT/.backend-url"
}

deploy_frontend() {
    echo -e "${YELLOW}[Frontend] Firebase Hosting 배포 시작...${NC}"
    cd "$PROJECT_ROOT/frontend"

    # Backend URL 가져오기
    if [ -f "$PROJECT_ROOT/.backend-url" ]; then
        BACKEND_URL=$(cat "$PROJECT_ROOT/.backend-url")
    else
        BACKEND_URL=$(gcloud run services describe jobchat-api \
            --region $REGION \
            --project $PROJECT_ID \
            --format 'value(status.url)' 2>/dev/null || echo "http://localhost:8000")
    fi

    # .env.production 생성
    echo "VITE_API_URL=$BACKEND_URL" > .env.production

    # 의존성 설치 및 빌드
    npm install
    npm run build

    # Firebase 배포
    firebase deploy --only hosting --project $PROJECT_ID

    echo -e "${GREEN}[Frontend] 배포 완료${NC}"
}

deploy_crawler() {
    echo -e "${YELLOW}[Crawler] Cloud Run Jobs 배포 시작...${NC}"
    cd "$PROJECT_ROOT/crawler"

    # 이미지 빌드 및 푸시
    gcloud builds submit \
        --tag gcr.io/$PROJECT_ID/jobchat-crawler \
        --project $PROJECT_ID

    # Cloud Run Job 생성/업데이트
    if gcloud run jobs describe jobchat-crawler --region $REGION --project $PROJECT_ID > /dev/null 2>&1; then
        gcloud run jobs update jobchat-crawler \
            --image gcr.io/$PROJECT_ID/jobchat-crawler \
            --region $REGION \
            --project $PROJECT_ID
    else
        gcloud run jobs create jobchat-crawler \
            --image gcr.io/$PROJECT_ID/jobchat-crawler \
            --region $REGION \
            --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT_ID,ENVIRONMENT=production" \
            --memory 1Gi \
            --cpu 1 \
            --task-timeout 3600 \
            --max-retries 1 \
            --project $PROJECT_ID
    fi

    # Cloud Scheduler 설정 (매일 새벽 3시 KST = UTC 18:00 전날)
    if ! gcloud scheduler jobs describe crawl-daily --location $REGION --project $PROJECT_ID > /dev/null 2>&1; then
        gcloud scheduler jobs create http crawl-daily \
            --location $REGION \
            --schedule "0 18 * * *" \
            --time-zone "UTC" \
            --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/jobchat-crawler:run" \
            --http-method POST \
            --oauth-service-account-email "${PROJECT_ID}@appspot.gserviceaccount.com" \
            --project $PROJECT_ID
    fi

    echo -e "${GREEN}[Crawler] 배포 완료${NC}"
}

# 메인 로직
case "${1:-all}" in
    backend)
        deploy_backend
        ;;
    frontend)
        deploy_frontend
        ;;
    crawler)
        deploy_crawler
        ;;
    all)
        deploy_backend
        deploy_frontend
        deploy_crawler
        ;;
    *)
        echo "사용법: $0 [backend|frontend|crawler|all]"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}배포 완료!${NC}"
echo -e "${GREEN}========================================${NC}"
