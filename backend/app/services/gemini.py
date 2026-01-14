"""Gemini 서비스 - V6 (Simple Agentic)

LLM을 파라미터 추출기가 아닌 자율적 판단자로 활용합니다.
- 정보 부족시: 자연스럽게 질문
- 정보 충분시: search_jobs 함수 호출
- 후속 대화: LLM이 판단하여 적절히 처리

Gemini 3 Flash + google.genai SDK 사용
"""

import logging
from typing import Any, Dict, List

from google import genai
from google.genai import types

from app.config import settings
from app.services.job_search import search_jobs_with_commute, format_job_results, _matches_company_location

logger = logging.getLogger(__name__)


# =============================================================================
# System Prompt - V6 Simple Agentic (Reasoning Model Optimized)
# =============================================================================
SYSTEM_PROMPT_TEMPLATE = """
당신은 채용공고 검색 전문가 "잡챗"입니다.
{user_location_info}

## 핵심 목표
사용자가 원하는 채용공고를 찾아주는 것. 대화 맥락을 이해하고 자율적으로 판단하세요.

## 사용 가능한 함수

### search_jobs: 채용공고 검색
- job_keywords: 직무 키워드 (필수)
- salary_min: 최소 연봉, 만원 단위 (필수). "3천"=3000, "무관"=0
- company_location: 회사 위치 필터 (선택). "강남역", "서초구" 등
- commute_max_minutes: 통근시간 제한 (선택). 사용자가 명시할 때만

### filter_results: 이전 검색 결과 필터링
- 기존 결과에서 조건 추가할 때 사용 (연봉 상향, 지역 한정 등)

## 판단 기준

1. **검색 실행 조건**: 직무 + 연봉 정보가 있으면 search_jobs 호출
2. **정보 부족 시**: 자연스럽게 질문 (연봉만 물어보면 됨)
3. **후속 대화**: 대화 맥락을 파악하여 적절히 판단
   - 조건 강화 (더 좁히기) → filter_results
   - 조건 완화/변경 (더 넓히기, 직무 변경) → search_jobs
4. **이전 검색 맥락 유지**: 후속 요청 시 이전 직무/연봉 기억하고 활용

## 응답 원칙
- 검색 결과는 간결하게: "총 N건을 찾았습니다" 정도
- 상세 목록은 프론트엔드가 표시하므로 나열하지 마세요
- 가상의 결과를 만들지 마세요 - 반드시 함수 호출
- 이모지 사용 금지
"""


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
        self.last_search_results: List[Dict] = []  # 최대 100건 저장
        self.last_search_params: Dict = {}
        self.displayed_count: int = 0  # 이미 보여준 개수
        self.history: List[types.Content] = []  # 대화 히스토리
        self.user_location: Dict[str, Any] = None  # 사용자 위치

    def save_search(self, results: List[Dict], params: Dict):
        """검색 결과 저장 (최대 100건)"""
        self.last_search_results = results[:100]
        self.last_search_params = params
        self.displayed_count = 0

    def get_next_batch(self, batch_size: int = 50) -> List[Dict]:
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
        salary_min: int = None,
        salary_max: int = None,
        commute_max_minutes: int = None,
        company_location: str = None
    ) -> List[Dict]:
        """캐시된 결과를 필터링하여 반환

        정책:
        - salary_min > 0 이면: 명시된 연봉이 있고 조건 충족하는 공고만 (회사내규 제외)
        - company_location이 있으면: 해당 지역 회사만 포함
        """
        filtered = []
        for job in self.last_search_results:
            # 연봉 필터 - 명시된 연봉만 포함 (회사내규 제외)
            if salary_min is not None and salary_min > 0:
                job_salary = job.get("salary_min")
                # 연봉 정보 없으면 (회사내규) 제외
                if job_salary is None:
                    continue
                # 연봉이 조건 미달이면 제외
                if job_salary < salary_min:
                    continue

            if salary_max is not None:
                job_salary = job.get("salary_max") or job.get("salary_min")
                if job_salary and job_salary > salary_max:
                    continue

            # 통근시간 필터
            if commute_max_minutes is not None:
                commute = job.get("commute_minutes")
                if commute is None or commute > commute_max_minutes:
                    continue

            # 회사 위치 필터
            if company_location and not _matches_company_location(job, company_location):
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

    def _build_system_prompt(self, user_location: Dict[str, Any] = None) -> str:
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

    async def process_message(
        self,
        message: str,
        conversation_id: str = "",
        user_location: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
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

            # Function Call 확인
            function_call = self._extract_function_call(response)

            if function_call and function_call.name == "search_jobs":
                # 검색 실행
                params = dict(function_call.args) if function_call.args else {}

                # 사용자 위치 (통근시간 계산용 - 항상 사용자 현재 위치 사용)
                user_loc = getattr(memory, 'user_location', None) or user_location
                commute_origin = ""
                if user_loc:
                    if user_loc.get("address"):
                        commute_origin = user_loc["address"]
                    else:
                        commute_origin = f"{user_loc['latitude']},{user_loc['longitude']}"

                # 회사 위치 필터 (LLM이 설정한 경우)
                company_location = params.get("company_location", "")

                logger.info(f"search_jobs 호출: keywords={params.get('job_keywords')}, "
                           f"salary={params.get('salary_min')}, company_loc={company_location}, "
                           f"commute_from={commute_origin}")

                # 통근시간 필터 (사용자가 명시한 경우만)
                commute_max = params.get("commute_max_minutes")  # None이면 통근시간 계산 안 함

                logger.info(f"commute_max_minutes={commute_max}")

                # 검색 수행
                search_result = await search_jobs_with_commute(
                    job_keywords=params.get("job_keywords", []),
                    salary_min=params.get("salary_min", 0),
                    salary_max=params.get("salary_max"),
                    commute_origin=commute_origin if commute_max else "",  # 통근 필터 없으면 origin도 불필요
                    commute_max_minutes=commute_max,  # None이면 통근시간 계산/필터 건너뜀
                    company_location=company_location  # 회사 위치 필터
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

            elif function_call and function_call.name == "filter_results":
                # 기존 결과 필터링
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

                # 필터링 수행
                filtered_jobs = memory.filter_cached_results(
                    salary_min=params.get("salary_min"),
                    salary_max=params.get("salary_max"),
                    commute_max_minutes=params.get("commute_max_minutes"),
                    company_location=params.get("company_location")
                )

                # 필터링 결과를 새로운 캐시로 저장
                original_count = len(memory.last_search_results)
                memory.save_search(filtered_jobs, {**memory.last_search_params, **params})

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
                    "filter_params": params,
                    "success": True
                }

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

    async def get_more_results(self, conversation_id: str) -> Dict[str, Any]:
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
                "displayed": memory.displayed_count,
                "has_more": memory.has_more(),
                "remaining": memory.get_remaining_count()
            },
            "success": True
        }

    def _format_jobs_for_llm(self, jobs: List[Dict]) -> List[str]:
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
