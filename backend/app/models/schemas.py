"""Pydantic 스키마 정의"""

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


class ChatResponse(BaseModel):
    """채팅 응답 모델"""
    success: bool
    response: str
    jobs: list[JobItem]
    total_count: int
    search_params: dict[str, Any]
    conversation_id: str
    error: Optional[str] = None


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
