"""Pydantic 스키마 정의 - V6 (Simple Agentic)"""

from pydantic import BaseModel, Field
from typing import Optional, Any, List


class UserLocation(BaseModel):
    """사용자 위치 정보"""
    latitude: float = Field(description="위도")
    longitude: float = Field(description="경도")
    address: Optional[str] = Field(None, description="역지오코딩된 주소")


class ChatRequest(BaseModel):
    """채팅 요청 모델"""
    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="사용자 메시지"
    )
    conversation_id: Optional[str] = Field(
        None,
        description="대화 ID (연속 대화용)"
    )
    user_location: Optional[UserLocation] = Field(
        None,
        description="사용자 현재 위치 (브라우저 geolocation)"
    )


class JobItem(BaseModel):
    """채용공고 아이템"""
    id: str
    company_name: str
    title: str
    location: str
    salary_text: str = Field(alias="salary", default="협의")
    experience_type: str = Field(alias="experience", default="")
    employment_type: str = ""
    deadline: str = ""
    url: str = ""
    # V6: 통근시간 정보
    commute_minutes: Optional[int] = Field(
        default=None,
        description="예상 통근시간 (분)"
    )
    commute_text: Optional[str] = Field(
        default=None,
        description="통근시간 텍스트 (예: '약 30분')"
    )

    class Config:
        populate_by_name = True


class PaginationInfo(BaseModel):
    """페이지네이션 정보 - V6"""
    total_count: int = Field(description="총 결과 수")
    displayed: int = Field(default=0, description="표시된 결과 수")
    has_more: bool = Field(default=False, description="더보기 가능 여부")
    remaining: int = Field(default=0, description="남은 결과 수")


class ChatResponse(BaseModel):
    """채팅 응답 모델 - V6"""
    success: bool
    response: str
    jobs: List[JobItem]
    pagination: Optional[PaginationInfo] = None
    search_params: dict[str, Any] = Field(
        default_factory=dict,
        description="검색 파라미터 (job_keywords, salary_min, commute_origin 등)"
    )
    conversation_id: str = ""
    error: Optional[str] = None


class MoreResultsRequest(BaseModel):
    """더보기 요청 모델"""
    conversation_id: str = Field(
        ...,
        description="대화 ID"
    )


class MoreResultsResponse(BaseModel):
    """더보기 응답 모델"""
    success: bool
    response: str = ""
    jobs: List[JobItem]
    pagination: Optional[PaginationInfo] = None
    has_more: bool = False


class HealthResponse(BaseModel):
    """헬스체크 응답"""
    status: str
    version: str
    environment: str
    services: dict[str, str]


class StatsResponse(BaseModel):
    """통계 응답"""
    total_jobs: int
    active_jobs: int
    last_crawl: Optional[str]


