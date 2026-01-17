"""채팅 API 라우터 - V6 (Simple Agentic)"""

import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    JobItem,
    PaginationInfo,
    MoreResultsRequest,
    MoreResultsResponse
)
from app.models.types import FormattedJobDict, UserLocationDict
from app.services.gemini import gemini_service

router = APIRouter()
logger = logging.getLogger(__name__)


def _create_job_item(job: FormattedJobDict) -> JobItem:
    """딕셔너리에서 JobItem 생성"""
    return JobItem(
        id=job.get("id", ""),
        company_name=job.get("company_name", ""),
        title=job.get("title", ""),
        location=job.get("location", ""),
        salary=job.get("salary_text", "협의"),
        experience=job.get("experience_type", ""),
        employment_type=job.get("employment_type", ""),
        deadline=job.get("deadline", ""),
        url=job.get("url", ""),
        commute_minutes=job.get("commute_minutes"),
        commute_text=job.get("commute_text", ""),
        # 디버깅/분석용 필드
        job_keywords=job.get("job_keywords", []),
        job_type_raw=job.get("job_type_raw", "")
    )


def _convert_jobs(raw_jobs: List[FormattedJobDict]) -> List[JobItem]:
    """딕셔너리 리스트를 JobItem 리스트로 변환"""
    jobs = []
    for job in raw_jobs:
        try:
            jobs.append(_create_job_item(job))
        except Exception as e:
            logger.warning(f"JobItem 생성 실패: {e}")
    return jobs


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    사용자 메시지를 받아 AI 응답과 매칭된 채용공고 반환

    V6 Simple Agentic 아키텍처:
    - LLM이 자율적으로 판단하여 정보 수집 또는 검색 실행
    - 필수 정보: 직무, 연봉, 통근 기준점
    - 통근시간: 지하철 기반 계산 (비용 $0)

    Args:
        request.message: 자연어 채용 조건
        request.conversation_id: 대화 ID (연속 대화용)

    Returns:
        AI 응답, 채용공고 리스트 (통근시간 포함), 페이지네이션 정보
    """
    try:
        # 대화 ID 생성 또는 사용
        conversation_id = request.conversation_id or str(uuid.uuid4())

        # 입력 검증
        if not request.message or not request.message.strip():
            raise HTTPException(status_code=400, detail="메시지를 입력해주세요.")

        if len(request.message) > 1000:
            raise HTTPException(status_code=400, detail="메시지가 너무 깁니다. (최대 1000자)")

        # 사용자 위치 정보 추출
        user_location: Optional[UserLocationDict] = None
        if request.user_location:
            user_location = {
                "latitude": request.user_location.latitude,
                "longitude": request.user_location.longitude,
                "address": request.user_location.address or ""
            }

        # Gemini 처리 (V6: Simple Agentic)
        result = await gemini_service.process_message(
            message=request.message.strip(),
            conversation_id=conversation_id,
            user_location=user_location
        )

        if not result["success"]:
            logger.error(f"Gemini 처리 실패: {result.get('error')}")

        # 응답 구성
        jobs = _convert_jobs(result.get("jobs", []))

        pagination = None
        if result.get("pagination"):
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


@router.post("/chat/more", response_model=MoreResultsResponse)
async def load_more(request: MoreResultsRequest):
    """
    캐시된 검색 결과에서 추가 결과 로드 (LLM 호출 없음)

    이 엔드포인트는 /chat에서 검색한 결과를 메모리에서 가져옵니다.
    AI를 다시 호출하지 않으므로 빠르고 비용이 들지 않습니다.

    Args:
        request.conversation_id: 대화 ID

    Returns:
        추가 검색 결과 (최대 50건)
    """
    try:
        result = await gemini_service.get_more_results(
            conversation_id=request.conversation_id
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=404,
                detail=result.get("response", "검색 결과를 찾을 수 없습니다.")
            )

        # 응답 구성
        jobs = _convert_jobs(result.get("jobs", []))

        pagination = None
        if result.get("pagination"):
            pagination = PaginationInfo(**result["pagination"])

        return MoreResultsResponse(
            success=True,
            response=result.get("response", ""),
            jobs=jobs,
            pagination=pagination,
            has_more=result.get("pagination", {}).get("has_more", False)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Load More API 오류: {e}")
        raise HTTPException(status_code=500, detail="서비스 오류가 발생했습니다.")
