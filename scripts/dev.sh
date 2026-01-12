#!/bin/bash

# JobChat 로컬 개발 서버 실행 스크립트
# 사용법: ./scripts/dev.sh [backend|frontend|all]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

start_backend() {
    echo -e "${YELLOW}[Backend] 서버 시작...${NC}"
    cd "$PROJECT_ROOT/backend"

    # 가상환경 확인
    if [ ! -d "venv" ]; then
        echo "가상환경 생성 중..."
        python3 -m venv venv
    fi

    source venv/bin/activate

    # 의존성 설치
    pip install -q -r requirements.txt

    # .env 확인
    if [ ! -f ".env" ]; then
        cp .env.example .env
        echo -e "${YELLOW}.env 파일을 생성했습니다. API 키를 설정해주세요.${NC}"
    fi

    # 서버 시작
    uvicorn app.main:app --reload --port 8000
}

start_frontend() {
    echo -e "${YELLOW}[Frontend] 서버 시작...${NC}"
    cd "$PROJECT_ROOT/frontend"

    # 의존성 설치
    if [ ! -d "node_modules" ]; then
        npm install
    fi

    # .env 확인
    if [ ! -f ".env" ]; then
        cp .env.example .env
    fi

    # 개발 서버 시작
    npm run dev
}

case "${1:-all}" in
    backend)
        start_backend
        ;;
    frontend)
        start_frontend
        ;;
    all)
        echo -e "${GREEN}백엔드와 프론트엔드를 별도 터미널에서 실행하세요:${NC}"
        echo ""
        echo "터미널 1: ./scripts/dev.sh backend"
        echo "터미널 2: ./scripts/dev.sh frontend"
        ;;
    *)
        echo "사용법: $0 [backend|frontend|all]"
        exit 1
        ;;
esac
