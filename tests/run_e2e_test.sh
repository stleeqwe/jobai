#!/bin/bash
# 통근시간 E2E 테스트 실행 스크립트

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "========================================"
echo "🚇 통근시간 E2E 테스트"
echo "========================================"

# 1. 서버 상태 확인
echo ""
echo "1. 서버 상태 확인..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "   ✅ 백엔드 서버 실행 중"
else
    echo "   ❌ 백엔드 서버가 실행되지 않았습니다."
    echo ""
    echo "   서버를 시작하려면:"
    echo "   cd $PROJECT_ROOT/backend"
    echo "   source venv/bin/activate"
    echo "   uvicorn app.main:app --reload"
    exit 1
fi

# 2. 빠른 API 테스트
echo ""
echo "2. 빠른 API 테스트..."
echo ""

# 건대입구역 테스트
echo "   🔍 건대입구역 30분 이내 검색..."
RESULT=$(curl -s -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "건대입구역에서 30분 이내 개발자 연봉 무관", "page": 1, "page_size": 3}')

# jq가 있으면 파싱, 없으면 raw 출력
if command -v jq &> /dev/null; then
    echo "$RESULT" | jq -r '.jobs[:3][] | "      [\(.travel_time_text // "없음")] \(.title[:30])"' 2>/dev/null || echo "      (파싱 실패)"
else
    echo "      결과: $(echo "$RESULT" | grep -o '"travel_time_text":"[^"]*"' | head -3)"
fi

# 9호선 테스트
echo ""
echo "   🔍 여의도역 40분 이내 검색 (9호선)..."
RESULT=$(curl -s -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "여의도역에서 40분 이내 마케터 연봉 무관", "page": 1, "page_size": 3}')

if command -v jq &> /dev/null; then
    echo "$RESULT" | jq -r '.jobs[:3][] | "      [\(.travel_time_text // "없음")] \(.title[:30])"' 2>/dev/null || echo "      (파싱 실패)"
else
    echo "      결과: $(echo "$RESULT" | grep -o '"travel_time_text":"[^"]*"' | head -3)"
fi

# 신분당선 테스트
echo ""
echo "   🔍 판교역 50분 이내 검색 (신분당선)..."
RESULT=$(curl -s -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "판교역에서 50분 이내 개발자 연봉 무관", "page": 1, "page_size": 3}')

if command -v jq &> /dev/null; then
    echo "$RESULT" | jq -r '.jobs[:3][] | "      [\(.travel_time_text // "없음")] \(.title[:30])"' 2>/dev/null || echo "      (파싱 실패)"
else
    echo "      결과: $(echo "$RESULT" | grep -o '"travel_time_text":"[^"]*"' | head -3)"
fi

# 3. 전체 테스트 (선택)
echo ""
echo "========================================"
echo "3. 전체 E2E 테스트 실행"
echo "========================================"
echo ""

cd "$PROJECT_ROOT"
python3 tests/test_e2e_commute.py

echo ""
echo "========================================"
echo "테스트 완료!"
echo "========================================"
