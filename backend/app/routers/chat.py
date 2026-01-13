"""채팅 API 라우터 - V3 (3-Stage Sequential Filter with Maps API)"""

import uuid
import logging
from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    JobItem,
    PaginationInfo,
    LoadMoreRequest,
    LoadMoreResponse
)
from app.services.gemini import gemini_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    사용자 메시지를 받아 AI 응답과 매칭된 채용공고 반환

    V3 아키텍처:
    - Phase 0: 필수 정보 수집 (직무, 연봉, 지역)
    - Stage 1: 직무 필터 (AI 의미적 매칭)
    - Stage 2: 연봉 필터 (DB, NULL 포함)
    - Stage 3: 지역 필터 (Maps API 이동시간)

    Args:
        request.message: 자연어 채용 조건
        request.page: 페이지 번호 (기본 1)
        request.page_size: 페이지당 결과 수 (기본 20)

    Returns:
        AI 응답, 채용공고 리스트 (이동시간 포함), 페이지네이션 정보
    """
    try:
        # 대화 ID 생성 또는 사용
        conversation_id = request.conversation_id or str(uuid.uuid4())

        # 입력 검증
        if not request.message or not request.message.strip():
            raise HTTPException(status_code=400, detail="메시지를 입력해주세요.")

        if len(request.message) > 1000:
            raise HTTPException(status_code=400, detail="메시지가 너무 깁니다. (최대 1000자)")

        # 사용자 좌표 (있으면)
        user_coords = None
        if request.user_lat is not None and request.user_lng is not None:
            user_coords = (request.user_lat, request.user_lng)

        # Gemini 처리 (V3: 3-Stage Filter + 대화 컨텍스트 유지)
        result = await gemini_service.process_message(
            message=request.message.strip(),
            conversation_id=conversation_id,
            page=request.page,
            page_size=request.page_size,
            user_coordinates=user_coords
        )

        if not result["success"]:
            logger.error(f"Gemini 처리 실패: {result.get('error')}")

        # 응답 구성
        jobs = [JobItem(**job) for job in result["jobs"]]
        pagination = PaginationInfo(**result["pagination"])

        return ChatResponse(
            success=result["success"],
            response=result["response"],
            jobs=jobs,
            pagination=pagination,
            search_params=result.get("search_params", {}),
            conversation_id=conversation_id,
            error=result.get("error")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Chat API 오류: {e}")
        raise HTTPException(status_code=500, detail="서비스 오류가 발생했습니다.")


@router.post("/chat/more", response_model=LoadMoreResponse)
async def load_more(request: LoadMoreRequest):
    """
    캐시된 검색 결과에서 추가 페이지 로드 (AI 재호출 없음)

    이 엔드포인트는 /chat에서 검색한 결과를 캐시에서 가져옵니다.
    AI를 다시 호출하지 않으므로 빠르고 비용이 들지 않습니다.

    Args:
        request.conversation_id: 대화 ID
        request.page: 페이지 번호
        request.page_size: 페이지당 결과 수

    Returns:
        캐시된 검색 결과의 해당 페이지
    """
    try:
        result = gemini_service.get_cached_page(
            conversation_id=request.conversation_id,
            page=request.page,
            page_size=request.page_size
        )

        if result is None:
            raise HTTPException(
                status_code=404,
                detail="검색 결과를 찾을 수 없습니다. 새로 검색해주세요."
            )

        jobs = [JobItem(**job) for job in result["jobs"]]
        pagination = PaginationInfo(**result["pagination"])

        return LoadMoreResponse(
            success=True,
            jobs=jobs,
            pagination=pagination,
            search_params=result.get("search_params", {})
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Load More API 오류: {e}")
        raise HTTPException(status_code=500, detail="서비스 오류가 발생했습니다.")
