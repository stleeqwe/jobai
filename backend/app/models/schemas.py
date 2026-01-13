"""Pydantic 스키마 정의 - V3 (3-Stage Filter + Maps API)"""

from pydantic import BaseModel, Field
from typing import Optional, Any


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
    page: int = Field(
        default=1,
        ge=1,
        description="페이지 번호 (기본 1)"
    )
    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="페이지당 결과 수 (기본 20, 최대 100)"
    )
    # 사용자 GPS 좌표 (Geolocation API)
    user_lat: Optional[float] = Field(
        None,
        description="사용자 위도"
    )
    user_lng: Optional[float] = Field(
        None,
        description="사용자 경도"
    )


class JobItem(BaseModel):
    """채용공고 아이템"""
    id: str
    company_name: str
    title: str
    location: str
    salary: str
    experience: str
    employment_type: str
    deadline: str
    url: str
    # V3: Maps API 이동시간 정보
    travel_time_minutes: Optional[int] = Field(
        default=None,
        description="예상 이동시간 (분)"
    )
    travel_time_text: Optional[str] = Field(
        default=None,
        description="이동시간 텍스트 (예: '15분')"
    )


class PaginationInfo(BaseModel):
    """페이지네이션 정보"""
    page: int = Field(description="현재 페이지 번호")
    page_size: int = Field(description="페이지당 결과 수")
    total_count: int = Field(description="총 결과 수")
    total_pages: int = Field(description="총 페이지 수")
    has_next: bool = Field(description="다음 페이지 존재 여부")
    has_prev: bool = Field(description="이전 페이지 존재 여부")


class ChatResponse(BaseModel):
    """채팅 응답 모델 - V3 (3-Stage Filter)"""
    success: bool
    response: str
    jobs: list[JobItem]
    pagination: PaginationInfo
    search_params: dict[str, Any] = Field(
        default_factory=dict,
        description="V3 검색 파라미터 (job_type, salary_min, user_location, max_commute_minutes)"
    )
    conversation_id: str
    error: Optional[str] = None

    # 하위 호환성을 위한 total_count (deprecated)
    @property
    def total_count(self) -> int:
        return self.pagination.total_count


class LoadMoreRequest(BaseModel):
    """더 보기 요청 모델 (캐시 기반 페이지네이션)"""
    conversation_id: str = Field(
        ...,
        description="대화 ID"
    )
    page: int = Field(
        default=1,
        ge=1,
        description="페이지 번호"
    )
    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="페이지당 결과 수"
    )


class LoadMoreResponse(BaseModel):
    """더 보기 응답 모델"""
    success: bool
    jobs: list[JobItem]
    pagination: PaginationInfo
    search_params: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """헬스체크 응답"""
    status: str
    version: str
    services: dict[str, str]


class StatsResponse(BaseModel):
    """통계 응답"""
    total_jobs: int
    active_jobs: int
    last_crawl: Optional[str]
