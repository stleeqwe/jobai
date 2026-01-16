"""Gemini 서비스 - V6 (Simple Agentic)

LLM을 파라미터 추출기가 아닌 자율적 판단자로 활용합니다.
- 정보 부족시: 자연스럽게 질문
- 정보 충분시: search_jobs 함수 호출
- 후속 대화: LLM이 판단하여 적절히 처리

Gemini 3 Flash + google.genai SDK 사용
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from app.config import settings
from app.models.types import (
    JobDict,
    UserLocationDict,
    GeminiResultDict,
    MoreResultsDict,
    SearchParamsDict,
    PaginationDict
)
from app.services.job_search import (
    search_jobs_with_commute,
    format_job_results,
    _calculate_commute_times
)
from app.utils.filters import matches_salary, matches_company_location

logger = logging.getLogger(__name__)


# =============================================================================
# System Prompt - V6 Simple Agentic (외부 파일에서 로드)
# =============================================================================
def _load_system_prompt() -> str:
    """시스템 프롬프트를 외부 파일에서 로드"""
    prompt_path = Path(__file__).parent.parent / "prompts" / "system_prompt.txt"
    try:
        return prompt_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning(f"시스템 프롬프트 파일을 찾을 수 없습니다: {prompt_path}")
        return "당신은 채용공고 검색 전문가입니다."

SYSTEM_PROMPT_TEMPLATE = _load_system_prompt()


# =============================================================================
# Function Declaration - V6 (google.genai 형식)
# =============================================================================
SEARCH_JOBS_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="search_jobs",
            description="채용공고를 검색합니다. 직무와 연봉 정보가 있으면 호출하세요. 통근시간은 사용자의 현재 위치에서 자동 계산됩니다.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "job_keywords": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.STRING),
                        description="직무 관련 키워드들. 예: ['프론트엔드', 'React', '웹개발']"
                    ),
                    "salary_min": types.Schema(
                        type=types.Type.INTEGER,
                        description="최소 연봉 (만원 단위). 무관이면 0. 예: 5000"
                    ),
                    "salary_max": types.Schema(
                        type=types.Type.INTEGER,
                        description="최대 연봉 (만원 단위). 제한 없으면 생략"
                    ),
                    "company_location": types.Schema(
                        type=types.Type.STRING,
                        description="회사 위치 필터. '강남역 근처', '서초구 내' 등 회사가 위치한 지역. 예: '강남역', '서초구', '판교'"
                    ),
                    "commute_max_minutes": types.Schema(
                        type=types.Type.INTEGER,
                        description="최대 통근시간 (분). 기본값 60. 예: 40"
                    )
                },
                required=["job_keywords", "salary_min"]
            )
        ),
        types.FunctionDeclaration(
            name="filter_results",
            description="이전 검색 결과를 추가 조건으로 필터링합니다. 사용자가 기존 결과에서 조건을 추가할 때 사용하세요. 예: '3천만원 이상만', '통근 30분 이내만', '강남쪽만'",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "salary_min": types.Schema(
                        type=types.Type.INTEGER,
                        description="최소 연봉 필터 (만원 단위). 예: 3000"
                    ),
                    "salary_max": types.Schema(
                        type=types.Type.INTEGER,
                        description="최대 연봉 필터 (만원 단위). 예: 5000"
                    ),
                    "commute_max_minutes": types.Schema(
                        type=types.Type.INTEGER,
                        description="최대 통근시간 필터 (분). 예: 30"
                    ),
                    "company_location": types.Schema(
                        type=types.Type.STRING,
                        description="회사 위치 필터. 예: '강남', '서초구', '판교'"
                    )
                },
                required=[]
            )
        )
    ]
)


class ConversationMemory:
    """세션별 대화 메모리"""

    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.last_search_results: List[JobDict] = []  # 최대 200건 저장
        self.last_search_params: SearchParamsDict = {}
        self.displayed_count: int = 0  # 이미 보여준 개수
        self.history: List[types.Content] = []  # 대화 히스토리
        self.user_location: Optional[UserLocationDict] = None  # 사용자 위치

    def save_search(self, results: List[JobDict], params: SearchParamsDict):
        """검색 결과 저장 (최대 200건)"""
        self.last_search_results = results[:200]
        self.last_search_params = params
        self.displayed_count = 0

    def get_next_batch(self, batch_size: int = 50) -> List[JobDict]:
        """다음 배치 반환 (더보기용)"""
        start = self.displayed_count
        end = start + batch_size
        batch = self.last_search_results[start:end]
        self.displayed_count = min(end, len(self.last_search_results))
        return batch

    def has_more(self) -> bool:
        """더 보여줄 결과가 있는지"""
        return self.displayed_count < len(self.last_search_results)

    def get_remaining_count(self) -> int:
        """남은 결과 수"""
        return len(self.last_search_results) - self.displayed_count

    def filter_cached_results(
        self,
        salary_min: Optional[int] = None,
        salary_max: Optional[int] = None,
        commute_max_minutes: Optional[int] = None,
        company_location: Optional[str] = None,
        jobs: Optional[List[JobDict]] = None
    ) -> List[JobDict]:
        """캐시된 결과를 필터링하여 반환

        정책:
        - salary_min > 0 이면: 명시된 연봉이 있고 조건 충족하는 공고만 (회사내규 제외)
        - company_location이 있으면: 해당 지역 회사만 포함
        """
        filtered = []
        source_jobs = jobs if jobs is not None else self.last_search_results
        for job in source_jobs:
            # 연봉 필터 (공용 유틸리티 사용)
            if not matches_salary(job, salary_min or 0, salary_max):
                continue

            # 통근시간 필터
            if commute_max_minutes is not None:
                commute = job.get("commute_minutes")
                if commute is None or commute > commute_max_minutes:
                    continue

            # 회사 위치 필터 (공용 유틸리티 사용)
            if company_location and not matches_company_location(job, company_location):
                continue

            filtered.append(job)

        return filtered

    def add_user_message(self, text: str):
        """사용자 메시지 추가"""
        self.history.append(types.Content(
            role="user",
            parts=[types.Part(text=text)]
        ))

    def add_model_message(self, text: str):
        """모델 메시지 추가"""
        self.history.append(types.Content(
            role="model",
            parts=[types.Part(text=text)]
        ))


class GeminiService:
    """Gemini 서비스 - V6 Simple Agentic (google.genai SDK)"""

    def __init__(self):
        # Gemini 클라이언트 초기화
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = settings.GEMINI_MODEL
        self._memories: Dict[str, ConversationMemory] = {}

    def _get_memory(self, conversation_id: str) -> ConversationMemory:
        """세션별 메모리 가져오기"""
        if conversation_id not in self._memories:
            self._memories[conversation_id] = ConversationMemory(conversation_id)
        return self._memories[conversation_id]

    def _build_system_prompt(self, user_location: Optional[UserLocationDict] = None) -> str:
        """사용자 위치 정보를 포함한 시스템 프롬프트 생성"""
        if user_location:
            address = user_location.get("address", "")
            if address:
                location_info = f"\n\n**현재 사용자 위치**: {address}"
            else:
                lat = user_location.get("latitude", 0)
                lng = user_location.get("longitude", 0)
                location_info = f"\n\n**현재 사용자 위치**: 좌표 ({lat:.4f}, {lng:.4f})"
        else:
            location_info = "\n\n**현재 사용자 위치**: 정보 없음 (위치를 명시해야 검색 가능)"

        return SYSTEM_PROMPT_TEMPLATE.format(user_location_info=location_info)

    async def _handle_search_jobs(
        self,
        function_call,
        memory: "ConversationMemory",
        user_location: Optional[UserLocationDict],
        config: types.GenerateContentConfig
    ) -> GeminiResultDict:
        """search_jobs 함수 호출 처리

        Args:
            function_call: Gemini Function Call 객체
            memory: 대화 메모리
            user_location: 사용자 위치 정보
            config: Gemini 설정

        Returns:
            검색 결과를 포함한 응답
        """
        params = dict(function_call.args) if function_call.args else {}

        # 후속 검색인 경우 이전 파라미터 병합 (직무가 동일/유사할 때)
        if memory.last_search_params:
            prev_keywords = set(k.lower() for k in memory.last_search_params.get("job_keywords", []))
            new_keywords = set(k.lower() for k in params.get("job_keywords", []))

            # 직무 키워드가 겹치면 후속 검색으로 판단
            keywords_overlap = bool(prev_keywords & new_keywords) if prev_keywords and new_keywords else False

            if keywords_overlap:
                logger.info(f"후속 검색 감지: 이전 params 병합 (overlap: {prev_keywords & new_keywords})")
                merged_params = {**memory.last_search_params}
                for key, value in params.items():
                    if value is not None:
                        merged_params[key] = value
                params = merged_params
                logger.info(f"병합 결과: {params}")

        # 사용자 위치 (통근시간 계산용)
        user_loc = getattr(memory, 'user_location', None) or user_location
        commute_origin = ""
        if user_loc:
            if user_loc.get("address"):
                commute_origin = user_loc["address"]
            else:
                commute_origin = f"{user_loc['latitude']},{user_loc['longitude']}"

        company_location = params.get("company_location", "")
        commute_max = params.get("commute_max_minutes")

        logger.info(f"search_jobs 호출: keywords={params.get('job_keywords')}, "
                   f"salary={params.get('salary_min')}, company_loc={company_location}, "
                   f"commute_from={commute_origin}, commute_max={commute_max}")

        # 검색 수행
        search_result = await search_jobs_with_commute(
            job_keywords=params.get("job_keywords", []),
            salary_min=params.get("salary_min", 0),
            salary_max=params.get("salary_max"),
            commute_origin=commute_origin,
            commute_max_minutes=commute_max,
            company_location=company_location
        )

        # 메모리에 저장
        memory.save_search(search_result["jobs"], params)

        # 첫 50건만 LLM에 전달
        first_batch = memory.get_next_batch(50)
        jobs_for_llm = self._format_jobs_for_llm(first_batch)

        # Function Response를 히스토리에 추가
        function_response_content = types.Content(
            role="user",
            parts=[types.Part(
                function_response=types.FunctionResponse(
                    name="search_jobs",
                    response={
                        "total_count": search_result["total_count"],
                        "returned_count": len(first_batch),
                        "has_more": memory.has_more(),
                        "jobs": jobs_for_llm
                    }
                )
            )]
        )
        memory.history.append(function_response_content)

        # 검색 결과를 LLM에 전달
        result_response = self.client.models.generate_content(
            model=self.model_name,
            contents=memory.history,
            config=config
        )

        response_text = self._extract_text(result_response)
        memory.add_model_message(response_text)

        return {
            "response": response_text,
            "jobs": format_job_results(first_batch),
            "pagination": {
                "total_count": search_result["total_count"],
                "displayed": len(first_batch),
                "has_more": memory.has_more(),
                "remaining": memory.get_remaining_count()
            },
            "search_params": params,
            "success": True
        }

    async def _handle_filter_results(
        self,
        function_call,
        memory: "ConversationMemory",
        user_location: Optional[UserLocationDict],
        config: types.GenerateContentConfig
    ) -> GeminiResultDict:
        """filter_results 함수 호출 처리

        Args:
            function_call: Gemini Function Call 객체
            memory: 대화 메모리
            user_location: 사용자 위치 정보
            config: Gemini 설정

        Returns:
            필터링 결과를 포함한 응답
        """
        params = dict(function_call.args) if function_call.args else {}

        logger.info(f"filter_results 호출: salary_min={params.get('salary_min')}, "
                   f"salary_max={params.get('salary_max')}, "
                   f"commute_max={params.get('commute_max_minutes')}, "
                   f"company_location={params.get('company_location')}")

        # 캐시된 결과가 없으면 안내
        if not memory.last_search_results:
            response_text = "먼저 검색을 해주세요. 어떤 직무의 채용공고를 찾고 계신가요?"
            memory.add_model_message(response_text)
            return {
                "response": response_text,
                "jobs": [],
                "pagination": None,
                "success": True
            }

        commute_max = params.get("commute_max_minutes")
        base_jobs = memory.last_search_results

        # 통근시간 필터 요청인데 캐시에 통근정보가 없으면 재계산
        if commute_max is not None:
            has_commute = any(
                job.get("commute_minutes") is not None for job in base_jobs
            )
            if not has_commute:
                user_loc = getattr(memory, "user_location", None)
                if not user_loc:
                    response_text = (
                        "통근시간 필터를 적용하려면 현재 위치 정보가 필요해요. "
                        "위치 권한을 허용하거나 출발지를 알려주세요."
                    )
                    memory.add_model_message(response_text)
                    return {
                        "response": response_text,
                        "jobs": [],
                        "pagination": None,
                        "success": True
                    }

                if user_loc.get("address"):
                    commute_origin = user_loc["address"]
                else:
                    commute_origin = f"{user_loc['latitude']},{user_loc['longitude']}"

                base_jobs = await _calculate_commute_times(
                    jobs=base_jobs,
                    origin=commute_origin,
                    max_minutes=commute_max
                )

        # 필터링 수행
        filtered_jobs = memory.filter_cached_results(
            salary_min=params.get("salary_min"),
            salary_max=params.get("salary_max"),
            commute_max_minutes=params.get("commute_max_minutes"),
            company_location=params.get("company_location"),
            jobs=base_jobs
        )

        # 필터링 결과를 새로운 캐시로 저장
        original_count = len(base_jobs)
        merged_params = {**memory.last_search_params, **params}
        memory.save_search(filtered_jobs, merged_params)

        # 첫 50건만 LLM에 전달
        first_batch = memory.get_next_batch(50)
        jobs_for_llm = self._format_jobs_for_llm(first_batch)

        # Function Response를 히스토리에 추가
        function_response_content = types.Content(
            role="user",
            parts=[types.Part(
                function_response=types.FunctionResponse(
                    name="filter_results",
                    response={
                        "original_count": original_count,
                        "filtered_count": len(filtered_jobs),
                        "returned_count": len(first_batch),
                        "has_more": memory.has_more(),
                        "jobs": jobs_for_llm
                    }
                )
            )]
        )
        memory.history.append(function_response_content)

        # 필터링 결과를 LLM에 전달
        result_response = self.client.models.generate_content(
            model=self.model_name,
            contents=memory.history,
            config=config
        )

        response_text = self._extract_text(result_response)
        memory.add_model_message(response_text)

        return {
            "response": response_text,
            "jobs": format_job_results(first_batch),
            "pagination": {
                "total_count": len(filtered_jobs),
                "displayed": len(first_batch),
                "has_more": memory.has_more(),
                "remaining": memory.get_remaining_count()
            },
            "search_params": merged_params,
            "success": True
        }

    async def process_message(
        self,
        message: str,
        conversation_id: str = "",
        user_location: Optional[UserLocationDict] = None,
    ) -> GeminiResultDict:
        """
        메시지 처리 - V6 Simple Agentic

        LLM이 자율적으로 판단:
        - 정보 부족 → 질문
        - 정보 충분 → search_jobs 호출
        - 후속 요청 → 적절히 처리

        Args:
            message: 사용자 메시지
            conversation_id: 대화 ID
            user_location: 사용자 위치 정보 (latitude, longitude, address)
        """
        try:
            memory = self._get_memory(conversation_id)
            memory.add_user_message(message)

            # 사용자 위치 정보를 메모리에 저장 (검색 시 사용)
            if user_location:
                memory.user_location = user_location

            # 시스템 프롬프트 생성 (사용자 위치 포함)
            system_prompt = self._build_system_prompt(user_location)

            # Gemini 3 Flash 설정 (thinking 활성화)
            # 참고: SDK 1.47.0에서는 thinking_level 미지원, thinking_budget 사용
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=[SEARCH_JOBS_TOOL],
                thinking_config=types.ThinkingConfig(thinking_budget=8192),
                max_output_tokens=8192
            )

            # 메시지 전송
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=memory.history,
                config=config
            )

            # Function Call 확인 및 분기 처리
            function_call = self._extract_function_call(response)

            if function_call and function_call.name == "search_jobs":
                return await self._handle_search_jobs(
                    function_call, memory, user_location, config
                )

            elif function_call and function_call.name == "filter_results":
                return await self._handle_filter_results(
                    function_call, memory, user_location, config
                )

            else:
                # Function Call 없음 - 텍스트 응답
                response_text = self._extract_text(response)
                memory.add_model_message(response_text)

                return {
                    "response": response_text,
                    "jobs": [],
                    "pagination": None,
                    "success": True
                }

        except Exception as e:
            logger.exception(f"process_message 오류: {e}")
            return {
                "response": "죄송해요, 처리 중 문제가 발생했어요. 다시 시도해주세요.",
                "jobs": [],
                "success": False,
                "error": str(e)
            }

    async def get_more_results(self, conversation_id: str) -> MoreResultsDict:
        """더보기 - LLM 호출 없이 메모리에서 반환"""
        memory = self._get_memory(conversation_id)

        if not memory.has_more():
            return {
                "response": "더 이상 결과가 없어요.",
                "jobs": [],
                "has_more": False,
                "success": True
            }

        next_batch = memory.get_next_batch(50)

        return {
            "response": f"추가 {len(next_batch)}건이에요.",
            "jobs": format_job_results(next_batch),
            "pagination": {
                "total_count": len(memory.last_search_results),
                "displayed": memory.displayed_count,
                "has_more": memory.has_more(),
                "remaining": memory.get_remaining_count()
            },
            "success": True
        }

    def _format_jobs_for_llm(self, jobs: List[JobDict]) -> List[str]:
        """LLM에 전달할 공고 목록 포맷팅 (토큰 최적화)"""
        lines = []
        for i, job in enumerate(jobs, 1):
            # 통근시간이 계산된 경우만 표시
            commute_min = job.get('commute_minutes')
            commute_part = f"통근 {commute_min}분 | " if commute_min else ""

            line = (
                f"{i}. {job.get('company_name', '')} - {job.get('title', '')}\n"
                f"   {commute_part}"
                f"{job.get('location_gugun', '') or job.get('location', '')} | "
                f"연봉 {job.get('salary_text', '협의')} | "
                f"{job.get('experience_type', '')}"
            )
            lines.append(line)
        return lines

    def _extract_function_call(self, response):
        """응답에서 Function Call 추출"""
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    return part.function_call
        return None

    def _extract_text(self, response) -> str:
        """응답에서 텍스트 추출"""
        if response.candidates:
            texts = []
            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    texts.append(part.text)
            return "".join(texts)
        return ""


def check_gemini() -> bool:
    """Gemini API 연결 상태 확인"""
    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents="테스트"
        )
        return bool(response.text)
    except Exception:
        return False


# 싱글톤
gemini_service = GeminiService()
