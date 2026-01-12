"""채팅 API 라우터"""

import uuid
import logging
from fastapi import APIRouter, HTTPException

from app.models.schemas import ChatRequest, ChatResponse, JobItem
from app.services.gemini import gemini_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    사용자 메시지를 받아 AI 응답과 매칭된 채용공고 반환

    - 자연어로 채용 조건 입력
    - Gemini가 조건 파싱 후 DB 검색
    - 검색 결과와 AI 응답 반환
    """
    try:
        # 대화 ID 생성 또는 사용
        conversation_id = request.conversation_id or str(uuid.uuid4())

        # 입력 검증
        if not request.message or not request.message.strip():
            raise HTTPException(status_code=400, detail="메시지를 입력해주세요.")

        if len(request.message) > 1000:
            raise HTTPException(status_code=400, detail="메시지가 너무 깁니다. (최대 1000자)")

        # Gemini 처리
        result = await gemini_service.process_message(request.message.strip())

        if not result["success"]:
            logger.error(f"Gemini 처리 실패: {result.get('error')}")

        # 응답 구성
        jobs = [JobItem(**job) for job in result["jobs"]]

        return ChatResponse(
            success=result["success"],
            response=result["response"],
            jobs=jobs,
            total_count=len(jobs),
            search_params=result["search_params"],
            conversation_id=conversation_id,
            error=result.get("error")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Chat API 오류: {e}")
        raise HTTPException(status_code=500, detail="서비스 오류가 발생했습니다.")
