#!/bin/bash

# JobChat GCP 환경 설정 스크립트
# 사용법: ./scripts/setup-gcp.sh [프로젝트ID]

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 프로젝트 ID 설정
PROJECT_ID=${1:-"jobchat-$(date +%s)"}
REGION="asia-northeast3"  # 서울

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}JobChat GCP 환경 설정${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "프로젝트 ID: ${YELLOW}${PROJECT_ID}${NC}"
echo -e "리전: ${YELLOW}${REGION}${NC}"
echo ""

# GCP 로그인 확인
echo -e "${YELLOW}[1/7] GCP 인증 확인...${NC}"
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -n1 > /dev/null 2>&1; then
    echo -e "${RED}GCP 로그인이 필요합니다.${NC}"
    gcloud auth login
fi
echo -e "${GREEN}✓ GCP 인증 완료${NC}"

# 프로젝트 생성
echo -e "${YELLOW}[2/7] GCP 프로젝트 생성...${NC}"
if gcloud projects describe $PROJECT_ID > /dev/null 2>&1; then
    echo -e "${YELLOW}프로젝트가 이미 존재합니다. 기존 프로젝트를 사용합니다.${NC}"
else
    gcloud projects create $PROJECT_ID --name="JobChat"
    echo -e "${GREEN}✓ 프로젝트 생성 완료${NC}"
fi

# 프로젝트 선택
gcloud config set project $PROJECT_ID

# 결제 계정 확인
echo -e "${YELLOW}[3/7] 결제 계정 확인...${NC}"
BILLING_ACCOUNT=$(gcloud billing accounts list --format="value(name)" | head -n1)
if [ -z "$BILLING_ACCOUNT" ]; then
    echo -e "${RED}결제 계정이 없습니다. GCP Console에서 결제 계정을 설정해주세요.${NC}"
    echo "https://console.cloud.google.com/billing"
    exit 1
fi
gcloud billing projects link $PROJECT_ID --billing-account=$BILLING_ACCOUNT
echo -e "${GREEN}✓ 결제 계정 연결 완료${NC}"

# API 활성화
echo -e "${YELLOW}[4/7] 필요한 API 활성화...${NC}"
gcloud services enable firestore.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable secretmanager.googleapis.com
echo -e "${GREEN}✓ API 활성화 완료${NC}"

# Firestore 생성
echo -e "${YELLOW}[5/7] Firestore 데이터베이스 생성...${NC}"
if gcloud firestore databases describe --format="value(name)" > /dev/null 2>&1; then
    echo -e "${YELLOW}Firestore가 이미 존재합니다.${NC}"
else
    gcloud firestore databases create --location=$REGION
    echo -e "${GREEN}✓ Firestore 생성 완료${NC}"
fi

# 서비스 계정 생성
echo -e "${YELLOW}[6/7] 서비스 계정 생성...${NC}"
SA_NAME="jobchat-dev"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if gcloud iam service-accounts describe $SA_EMAIL > /dev/null 2>&1; then
    echo -e "${YELLOW}서비스 계정이 이미 존재합니다.${NC}"
else
    gcloud iam service-accounts create $SA_NAME \
        --display-name="JobChat Development"
fi

# 권한 부여
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/datastore.user" \
    --quiet

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet

# 키 파일 생성
KEY_FILE="$HOME/jobchat-credentials.json"
if [ ! -f "$KEY_FILE" ]; then
    gcloud iam service-accounts keys create $KEY_FILE \
        --iam-account=$SA_EMAIL
    echo -e "${GREEN}✓ 서비스 계정 키 생성: ${KEY_FILE}${NC}"
else
    echo -e "${YELLOW}키 파일이 이미 존재합니다: ${KEY_FILE}${NC}"
fi

# .env 파일 생성
echo -e "${YELLOW}[7/7] 환경 변수 파일 생성...${NC}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cat > "$PROJECT_ROOT/.env" << EOF
# GCP Configuration
GOOGLE_CLOUD_PROJECT=${PROJECT_ID}
GOOGLE_APPLICATION_CREDENTIALS=${KEY_FILE}

# Gemini API (직접 입력 필요)
GEMINI_API_KEY=your-gemini-api-key-here

# Environment
ENVIRONMENT=development
DEBUG=true

# Backend
BACKEND_PORT=8000
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000

# Frontend
VITE_API_URL=http://localhost:8000

# Crawler
CRAWL_DELAY_SECONDS=1.0
MAX_PAGES=100
EOF

echo -e "${GREEN}✓ .env 파일 생성 완료${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}설정 완료!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "프로젝트 ID: ${YELLOW}${PROJECT_ID}${NC}"
echo -e "리전: ${YELLOW}${REGION}${NC}"
echo -e "서비스 계정: ${YELLOW}${SA_EMAIL}${NC}"
echo -e "키 파일: ${YELLOW}${KEY_FILE}${NC}"
echo ""
echo -e "${YELLOW}다음 단계:${NC}"
echo "1. .env 파일에서 GEMINI_API_KEY를 설정하세요"
echo "2. Firebase 설정: firebase login && firebase projects:addfirebase ${PROJECT_ID}"
echo ""
