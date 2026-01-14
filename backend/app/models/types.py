"""TypedDict 정의 - 내부 데이터 구조 타입 정의

Pydantic 모델은 API 응답용이고, TypedDict는 내부 처리용입니다.
Dict[str, Any] 대신 사용하여 타입 안전성을 높입니다.
"""

from typing import List, Optional, TypedDict


class CommuteDetail(TypedDict, total=False):
    """통근 상세 정보"""
    origin_station: str
    dest_station: str
    origin_walk: int
    dest_walk: int


class JobDict(TypedDict, total=False):
    """채용공고 딕셔너리 (DB에서 조회한 원본 데이터)

    Firestore에서 조회한 공고 데이터의 구조를 정의합니다.
    total=False로 설정하여 모든 필드를 선택적으로 처리합니다.
    """
    # 필수 필드
    id: str
    company_name: str
    title: str
    url: str

    # 직무 정보
    job_type_raw: str
    job_keywords: List[str]

    # 위치 정보
    location_full: str
    location_gugun: str
    nearest_station: str

    # 연봉 정보
    salary_text: str
    salary_min: Optional[int]
    salary_max: Optional[int]

    # 경력 정보
    experience_type: str
    experience_min: Optional[int]
    experience_max: Optional[int]

    # 기타 정보
    employment_type: str
    deadline: str
    is_active: bool

    # 통근시간 정보 (계산 후 추가됨)
    commute_minutes: Optional[int]
    commute_text: str
    commute_detail: CommuteDetail


class FormattedJobDict(TypedDict, total=False):
    """API 응답용 포맷된 채용공고

    format_job_results() 함수가 반환하는 구조입니다.
    """
    id: str
    company_name: str
    title: str
    location: str
    salary_text: str
    experience_type: str
    employment_type: str
    deadline: str
    url: str
    commute_minutes: Optional[int]
    commute_text: str


class UserLocationDict(TypedDict, total=False):
    """사용자 위치 정보"""
    latitude: float
    longitude: float
    address: str


class SearchResultDict(TypedDict):
    """검색 결과 (search_jobs_with_commute 반환값)"""
    jobs: List[JobDict]
    total_count: int
    filtered_by_commute: int


class PaginationDict(TypedDict, total=False):
    """페이지네이션 정보"""
    total_count: int
    displayed: int
    has_more: bool
    remaining: int


class SearchParamsDict(TypedDict, total=False):
    """검색 파라미터"""
    job_keywords: List[str]
    salary_min: int
    salary_max: Optional[int]
    commute_origin: str
    commute_max_minutes: Optional[int]
    company_location: str


class GeminiResultDict(TypedDict, total=False):
    """Gemini 서비스 응답"""
    response: str
    jobs: List[FormattedJobDict]
    pagination: Optional[PaginationDict]
    search_params: SearchParamsDict
    filter_params: SearchParamsDict
    success: bool
    error: str


class MoreResultsDict(TypedDict, total=False):
    """더보기 응답"""
    response: str
    jobs: List[FormattedJobDict]
    pagination: Optional[PaginationDict]
    has_more: bool
    success: bool
