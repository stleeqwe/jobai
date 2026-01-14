"""Gemini API 서비스 모듈 - V3.2 (Single Function Call)"""

import json
import logging
import re
import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool
from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.job_search import get_all_active_jobs, filter_by_salary, format_job_results
from app.services.subway import subway_service
from app.db import save_conversation_history, load_conversation_history

logger = logging.getLogger(__name__)

# API 키 설정
genai.configure(api_key=settings.GEMINI_API_KEY)


def _convert_proto_to_dict(proto_obj) -> Dict[str, Any]:
    """protobuf 객체를 Python dict로 변환"""
    result = {}
    for key, value in proto_obj.items():
        if hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
            try:
                result[key] = list(value)
            except:
                result[key] = value
        else:
            result[key] = value
    return result


# =============================================================================
# Single Function: 모든 파라미터를 한 번에 추출
# =============================================================================
SEARCH_JOBS_FUNCTION = FunctionDeclaration(
    name="search_jobs",
    description="""
    채용공고를 검색합니다. 사용자가 직무, 연봉, 위치 조건을 언급하면 호출하세요.
    모든 조건을 한 번에 파라미터로 전달합니다.
    """,
    parameters={
        "type": "object",
        "properties": {
            "job_type": {
                "type": "string",
                "description": "찾는 직무/직종 (예: '앱 개발자', '백엔드 엔지니어', 'UI/UX 디자이너')"
            },
            "salary_min": {
                "type": "integer",
                "description": "최소 연봉 (만원 단위). 0이면 연봉 무관. 예: 5000 = 5천만원"
            },
            "location_filter_type": {
                "type": "string",
                "enum": ["none", "proximity", "commute"],
                "description": "위치 필터 유형. none: 위치 조건 없음, proximity: 특정 장소 근처/부근 (반경 기반), commute: 통근시간 기반 (집/현재위치에서 몇 분)"
            },
            "proximity_location": {
                "type": "string",
                "description": "proximity일 때 기준 위치. 예: '강남역', '판교', '을지로'. 해당 장소 반경 내 공고 검색"
            },
            "proximity_km": {
                "type": "number",
                "description": "proximity일 때 반경 (km). 기본값 3. '바로 옆', '도보 거리'면 1, '근처'면 3, '주변'이면 5"
            },
            "commute_max_minutes": {
                "type": "integer",
                "description": "commute일 때 최대 통근시간 (분). 예: '30분 이내'→30, '1시간'→60"
            }
        },
        "required": ["job_type", "salary_min", "location_filter_type"]
    }
)


# =============================================================================
# System Prompt - 단순화
# =============================================================================
SYSTEM_PROMPT = """
너는 채용공고 검색을 도와주는 AI 어시스턴트 "잡챗"이야.

## 핵심 규칙 (매우 중요!)

1. 사용자가 직무와 연봉 조건을 모두 말하면 **즉시** search_jobs 함수를 호출해.
2. "잠시만요", "기다려주세요" 같은 말 없이 바로 함수를 호출해야 해.
3. **함수는 반드시 한 번만 호출해.** 여러 직무를 요청해도 하나의 search_jobs 호출에 모든 직무를 포함해.
4. **"개발자", "디자이너" 같은 넓은 직무도 그대로 검색해.** 구체적인 직무를 다시 묻지 마.

예시 (즉시 함수 호출):
- "마케터 찾아줘, 연봉 무관" → 즉시 search_jobs(job_type="마케터", salary_min=0)
- "개발자 또는 디자이너, 연봉 무관" → 즉시 search_jobs(job_type="개발자 또는 디자이너", salary_min=0)
- "디자이너 아니면 개발자, 연봉 무관" → 즉시 search_jobs(job_type="디자이너 아니면 개발자", salary_min=0)
- "내 위치에서 1시간 이내 개발자, 연봉 5천" → 즉시 search_jobs 호출

예시 (추가 질문 필요):
- "웹디자이너" → 연봉 정보 없음 → "희망 연봉 조건이 있으신가요?"
- "연봉 5천 이상 찾아줘" → 직무 없음 → "어떤 직무를 찾으시나요?"

## 검색 방법

search_jobs 함수 파라미터:

- job_type: 찾는 직무 (필수) - 여러 직무면 그대로 전달 (예: "개발자 아니면 디자이너")
- salary_min: 최소 연봉, 만원 단위 (필수, 무관이면 0)
- location_filter_type: 위치 필터 유형 (필수) - "none", "proximity", "commute" 중 하나

## 위치 필터 유형 구분 (매우 중요!)

### 1. none (위치 조건 없음)
사용자가 위치를 언급하지 않으면 "none"
- "앱 개발자 연봉 4천" → location_filter_type: "none"
- "디자이너 찾아줘, 연봉 무관" → location_filter_type: "none"

### 2. proximity (특정 장소 반경)
"근처", "부근", "주변", "가까운" 등 **특정 장소 주변**을 찾을 때
- "강남역 근처" → location_filter_type: "proximity", proximity_location: "강남역", proximity_km: 3
- "판교 부근 회사" → location_filter_type: "proximity", proximity_location: "판교", proximity_km: 3
- "을지로 주변" → location_filter_type: "proximity", proximity_location: "을지로", proximity_km: 5
- "신사동 가까운 곳" → location_filter_type: "proximity", proximity_location: "신사동", proximity_km: 3

### 3. commute (통근시간 기반)
"집에서", "우리집", "내 위치에서", "여기서", "X분 이내", "출퇴근" 등 **사용자 위치 기준 통근시간**을 따질 때
- "우리집에서 30분 이내" → location_filter_type: "commute", commute_max_minutes: 30
- "내 위치에서 1시간" → location_filter_type: "commute", commute_max_minutes: 60
- "여기서 40분 거리" → location_filter_type: "commute", commute_max_minutes: 40
- "출퇴근 가능한" → location_filter_type: "commute", commute_max_minutes: 60

### 핵심 구분법
- **"강남역 근처"** = 강남역 **주변에 위치한** 회사 찾기 → proximity
- **"강남역에서 30분"** = 강남역에서 출발해서 **30분 이내 도착** 가능한 회사 → commute
- **"집에서 강남역 근처"** = 강남역 주변 회사 중 집에서 통근 가능한 → proximity (강남역 기준)

## 연봉 처리

사용자가 연봉 조건을 언급하면 의미를 해석해서 salary_min 설정:
- 구체적인 금액 언급 → 해당 금액 (만원 단위)
- 조건 없음/유연함을 표현 → salary_min: 0 (예: 무관, 협상, 협의, 면접 후, 상관없음 등)

## 정보 수집

필요한 정보가 부족하면 친절하게 물어봐:
- 직무가 없으면: "어떤 직무를 찾으시나요?"
- 연봉이 없으면: "희망 연봉 조건이 있으신가요? (없으면 '무관'이라고 해주세요)"

위치 조건은 선택사항이야. 없으면 전국 검색.

## 응답 스타일

- 존댓말 사용
- 친근하고 자연스럽게
- 결과가 있으면 핵심 공고 몇 개 하이라이트
- 결과가 없으면 조건 완화 제안
"""


# =============================================================================
# Stage 1: 직무 필터용 프롬프트
# =============================================================================
SELECT_JOBS_BY_TYPE_PROMPT = """
다음 채용공고 목록에서 "{job_type}"에 해당하는 공고만 선별하세요.

## 핵심 원칙 (매우 중요!)
1. 제목과 직무 설명에 "{job_type}" 관련 키워드가 명확히 있어야만 포함
2. 의심스러우면 무조건 제외
3. "병리사", "간호사", "약사" 등 의료직은 절대 디자이너/개발자/마케터가 아님

### 직무 매칭 예시

**"프론트 앱 개발자" 또는 "앱 개발자"**
✅ 포함: Flutter, React Native, iOS, Android, 모바일 앱 개발
❌ 제외: 웹 프론트엔드, 백엔드, 디자이너, 기획자

**"백엔드 개발자" 또는 "서버 개발자"**
✅ 포함: Java 백엔드, Node.js, Python 서버, Spring, Django
❌ 제외: 프론트엔드, 앱 개발, 디자이너

**"웹 프론트엔드" 또는 "웹 개발자"**
✅ 포함: React, Vue.js, Angular, 웹퍼블리셔
❌ 제외: 앱 개발자, 백엔드, 디자이너

**"디자이너"**
✅ 포함: UI/UX 디자이너, 웹디자이너, 그래픽 디자이너, 제품 디자이너, 패션 디자이너, 인테리어 디자이너
❌ 제외: 개발자, 기획자, 마케터, 의료직(간호사, 병리사 등), 사무직, 영업직, 서비스직

**"마케터"**
✅ 포함: 퍼포먼스 마케터, 콘텐츠 마케터, 디지털 마케팅, 광고 기획
❌ 제외: 디자이너, 개발자, 의료직, 사무직

## 절대 포함하면 안 되는 직종
- 의료/보건: 간호사, 병리사, 약사, 의사, 물리치료사
- 서비스: 바리스타, 요리사, 미용사, 상담사
- 사무/행정: 경리, 총무, 비서, 회계
- 영업/판매: 영업사원, 판매원, 텔레마케터

## 후보 공고 목록
{candidates}

## 응답 형식
반드시 JSON 배열로만 응답하세요. 설명 없이 ID만:
["jk_123", "jk_456", ...]

관련 공고가 없으면:
[]
"""


# =============================================================================
# 직무 파싱용 프롬프트 (맥락 이해)
# =============================================================================
PARSE_JOB_TYPES_PROMPT = """
사용자의 직무 요청을 분석하여 검색할 직무 목록을 추출하세요.

입력: "{job_type_query}"

## 핵심 원칙
1. 명확히 다른 직무를 OR로 연결한 경우 → 분리
2. 같은 분야의 세부 조건/선호도인 경우 → 하나로 통합 (맥락 포함)

## 예시

입력: "웹디자이너 혹은 편집디자이너"
→ ["웹디자이너", "편집디자이너"]
(이유: 명확히 다른 두 직무를 OR로 연결)

입력: "개발자 아니면 디자이너"
→ ["개발자", "디자이너"]
(이유: 완전히 다른 직군)

입력: "디자이너 아니면 개발자, 연봉 무관"
→ ["디자이너", "개발자"]
(이유: 완전히 다른 직군, 연봉 조건은 무시)

입력: "풀스택 개발자, 특히 앱 풀스택, iOS Android 상관없어"
→ ["풀스택 개발자 (모바일 앱 중심)"]
(이유: 같은 풀스택 분야 + 세부 선호도 → 통합)

입력: "ai나 머신러닝 엔지니어, 데이터 사이언스 위주"
→ ["AI/ML/데이터 사이언스 엔지니어"]
(이유: 모두 데이터/AI 분야 → 통합)

입력: "마케터나 기획자, 스타트업 경험자"
→ ["마케터 (스타트업)", "기획자 (스타트업)"]
(이유: 다른 직무 + 공통 조건 → 분리 후 조건 적용)

입력: "프론트엔드 개발자"
→ ["프론트엔드 개발자"]
(이유: 단일 직무)

입력: "백엔드 개발자나 서버 개발자"
→ ["백엔드/서버 개발자"]
(이유: 같은 직무의 다른 표현 → 통합)

## 응답 형식
JSON 배열만 응답하세요:
["직무1", "직무2"]
"""


class GeminiService:
    """Gemini API 서비스 - V3.2 (Single Function Call)"""

    def __init__(self):
        # Single Function Call용 모델
        self.chat_model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            tools=[Tool(function_declarations=[SEARCH_JOBS_FUNCTION])],
            system_instruction=SYSTEM_PROMPT
        )
        # 직무 필터용 모델
        self.filter_model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL
        )
        # 대화 히스토리 저장소
        self._conversations: Dict[str, List] = {}
        # 검색 결과 캐시 (페이지네이션용)
        self._search_cache: Dict[str, Dict[str, Any]] = {}

    async def process_message(
        self,
        message: str,
        conversation_id: str = "",
        page: int = 1,
        page_size: int = 20,
        user_coordinates: Optional[tuple] = None
    ) -> Dict[str, Any]:
        """
        V3.2: Single Function Call

        모든 검색 조건(직무, 연봉, 위치)을 한 번의 Function Call로 추출
        위치 파싱은 Backend에서 별도 처리

        Args:
            message: 사용자 메시지
            conversation_id: 대화 ID
            page: 페이지 번호
            page_size: 페이지당 결과 수
            user_coordinates: 사용자 GPS 좌표 (lat, lng) - Geolocation API

        Returns:
            응답 데이터
        """
        try:
            # 대화 히스토리 복원 (Firestore 우선, 없으면 인메모리)
            history = self._conversations.get(conversation_id, [])
            if not history and conversation_id:
                # Firestore에서 로드 시도
                saved_data = await load_conversation_history(conversation_id)
                if saved_data and saved_data.get("history"):
                    logger.info(f"Firestore에서 대화 히스토리 로드: {conversation_id}")
                    # 직렬화된 히스토리를 Gemini Content 형식으로 재구성
                    history = self._reconstruct_history(saved_data["history"])

            chat = self.chat_model.start_chat(history=history)

            # 메시지 전송
            response = chat.send_message(message)

            search_params = {}
            final_jobs = []

            # Function Call 처리 (다중 function call 안전 처리)
            function_calls = self._extract_function_calls(response)

            if function_calls:
                # 다중 function call 경고
                if len(function_calls) > 1:
                    logger.warning(f"다중 Function Call 감지: {len(function_calls)}개. 첫 번째만 처리하고 모두에게 응답합니다.")

                # 첫 번째 search_jobs function call 처리
                search_call = None
                for fc in function_calls:
                    if fc.name == "search_jobs":
                        search_call = fc
                        break

                if search_call:
                    fn_args = _convert_proto_to_dict(search_call.args) if search_call.args else {}
                    logger.info(f"Function Call: search_jobs, args: {fn_args}")

                    # 파라미터 추출 (새로운 스키마)
                    job_type = fn_args.get("job_type", "")
                    salary_min = int(fn_args.get("salary_min", 0))
                    location_filter_type = fn_args.get("location_filter_type", "none")
                    proximity_location = fn_args.get("proximity_location", "")
                    proximity_km = float(fn_args.get("proximity_km", 3.0))
                    commute_max_minutes = int(fn_args.get("commute_max_minutes", 60))

                    search_params = {
                        "job_type": job_type,
                        "salary_min": salary_min,
                        "location_filter_type": location_filter_type,
                        "proximity_location": proximity_location,
                        "proximity_km": proximity_km,
                        "commute_max_minutes": commute_max_minutes,
                        "user_coordinates": user_coordinates
                    }

                    # 3-Stage 필터링 파이프라인 실행
                    result = await self._execute_search_pipeline(
                        job_type=job_type,
                        salary_min=salary_min,
                        location_filter_type=location_filter_type,
                        proximity_location=proximity_location,
                        proximity_km=proximity_km,
                        commute_max_minutes=commute_max_minutes,
                        user_coordinates=user_coordinates
                    )

                    final_jobs = result["jobs"]

                    # 검색 결과 캐시 저장 (페이지네이션용)
                    if conversation_id:
                        self._search_cache[conversation_id] = {
                            "jobs": final_jobs,
                            "search_params": search_params,
                            "response_text": ""  # 나중에 업데이트
                        }

                    # 모든 function call에 대해 응답 생성 (다중 function call 오류 방지)
                    response_data = {
                        "total_count": len(final_jobs),
                        "jobs": result["sample_jobs"],
                        "location_filtered": result.get("location_filtered", False),
                        "origins_used": result.get("origins", []),
                        "job_types_parsed": result.get("job_types_parsed", [])
                    }

                    # 각 function call에 대한 응답 파트 생성
                    response_parts = []
                    for fc in function_calls:
                        response_parts.append(
                            genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=fc.name,
                                    response=response_data
                                )
                            )
                        )

                    # AI에게 결과 전달
                    response = chat.send_message(
                        genai.protos.Content(parts=response_parts)
                    )

            # 최종 응답 텍스트 추출
            response_text = self._extract_text_response(response)

            # 대화 히스토리 저장 (인메모리 + Firestore)
            if conversation_id:
                self._conversations[conversation_id] = chat.history
                # Firestore에 비동기 저장 (실패해도 무시)
                try:
                    search_cache = self._search_cache.get(conversation_id)
                    await save_conversation_history(
                        conversation_id, chat.history, search_cache
                    )
                except Exception as e:
                    logger.warning(f"대화 히스토리 Firestore 저장 실패: {e}")

            # 페이지네이션
            total_count = len(final_jobs)
            total_pages = max(1, (total_count + page_size - 1) // page_size)
            page = max(1, min(page, total_pages))

            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_jobs = final_jobs[start_idx:end_idx]

            # 결과 포맷팅
            formatted_jobs = format_job_results(page_jobs)

            return {
                "response": response_text,
                "jobs": formatted_jobs,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_count": total_count,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                },
                "search_params": search_params,
                "success": True
            }

        except Exception as e:
            logger.exception(f"process_message 오류: {e}")
            return {
                "response": "죄송합니다. 처리 중 오류가 발생했습니다. 다시 시도해주세요.",
                "jobs": [],
                "pagination": self._empty_pagination(page_size),
                "search_params": {},
                "success": False,
                "error": str(e)
            }

    async def _execute_search_pipeline(
        self,
        job_type: str,
        salary_min: int,
        location_filter_type: str = "none",
        proximity_location: str = "",
        proximity_km: float = 3.0,
        commute_max_minutes: int = 60,
        user_coordinates: Optional[tuple] = None
    ) -> Dict[str, Any]:
        """
        3-Stage 검색 파이프라인 실행

        Stage 0: 직무 파싱 (AI) - 복수 직무 지원
        Stage 1: 직무 필터 (AI) - 각 직무별 실행 후 합집합
        Stage 2: 연봉 필터 (DB)
        Stage 3: 위치 필터 (유형별 처리)
            - none: 위치 필터 없음
            - proximity: 특정 장소 반경 내 (km 기반)
            - commute: 통근시간 기반 (GPS 필요)

        Args:
            job_type: 직무 유형
            salary_min: 최소 연봉
            location_filter_type: 위치 필터 유형 (none, proximity, commute)
            proximity_location: proximity일 때 기준 위치
            proximity_km: proximity일 때 반경 (km)
            commute_max_minutes: commute일 때 최대 통근시간 (분)
            user_coordinates: GPS 좌표 (lat, lng)

        Returns:
            필터링된 공고 목록
        """
        logger.info(f"Pipeline 시작: job_type={job_type}, salary_min={salary_min}, "
                   f"location_filter_type={location_filter_type}, proximity_location={proximity_location}, "
                   f"proximity_km={proximity_km}, commute_max_minutes={commute_max_minutes}")

        # 전체 활성 공고 가져오기
        all_jobs = await get_all_active_jobs()
        logger.info(f"전체 활성 공고: {len(all_jobs)}건")

        if not all_jobs:
            return {"jobs": [], "sample_jobs": [], "location_filtered": False, "job_types_parsed": []}

        # Stage 0: 직무 파싱 (복수 직무 지원)
        job_types = await self._parse_job_types(job_type)
        logger.info(f"Stage 0 (직무 파싱): {job_types}")

        # Stage 1: 직무 필터 (AI) - 각 직무별 실행 후 합집합
        stage1_jobs_dict = {}  # 중복 제거용

        for jt in job_types:
            filtered = await self._filter_by_job_type(jt, all_jobs)
            logger.info(f"Stage 1 '{jt}' 결과: {len(filtered)}건")
            for job in filtered:
                job_id = job.get("id")
                if job_id and job_id not in stage1_jobs_dict:
                    stage1_jobs_dict[job_id] = job

        stage1_jobs = list(stage1_jobs_dict.values())
        logger.info(f"Stage 1 (직무 필터 합집합): {len(stage1_jobs)}건")

        # Stage 2: 연봉 필터
        stage2_jobs = filter_by_salary(stage1_jobs, salary_min)
        logger.info(f"Stage 2 (연봉 필터): {len(stage2_jobs)}건")

        # Stage 3: 위치 필터 (유형별 처리)
        final_jobs = stage2_jobs
        location_filtered = False
        location_info = {}

        if location_filter_type == "none":
            # 위치 필터 없음
            logger.info("Stage 3: 위치 필터 없음 (none)")
            final_jobs = stage2_jobs

        elif location_filter_type == "proximity":
            # 특정 장소 반경 내 필터
            logger.info(f"Stage 3: 반경 필터 (proximity) - {proximity_location} 반경 {proximity_km}km")

            # 기준 위치 좌표 가져오기
            reference_coords = self._get_location_coordinates(proximity_location)
            if reference_coords:
                stage3_jobs = self._filter_by_proximity(
                    stage2_jobs, reference_coords, proximity_km
                )
                final_jobs = stage3_jobs
                location_filtered = True
                location_info = {
                    "type": "proximity",
                    "reference": proximity_location,
                    "radius_km": proximity_km
                }
                logger.info(f"Stage 3 (반경 필터): {len(stage3_jobs)}건")
            else:
                logger.warning(f"기준 위치 '{proximity_location}' 좌표를 찾을 수 없음")

        elif location_filter_type == "commute":
            # 통근시간 기반 필터 (GPS 필요)
            logger.info(f"Stage 3: 통근시간 필터 (commute) - 최대 {commute_max_minutes}분")

            if user_coordinates and subway_service.is_available():
                origin = f"{user_coordinates[0]},{user_coordinates[1]}"
                stage3_jobs = await subway_service.filter_jobs_by_travel_time(
                    stage2_jobs, origin, commute_max_minutes
                )
                stage3_jobs.sort(key=lambda x: x.get("travel_time_minutes", 999))
                final_jobs = stage3_jobs
                location_filtered = True
                location_info = {
                    "type": "commute",
                    "max_minutes": commute_max_minutes,
                    "origin": "내 위치 (GPS)"
                }
                logger.info(f"Stage 3 (통근시간 필터): {len(stage3_jobs)}건")
            else:
                logger.warning("GPS 좌표 없음 - 통근시간 필터 스킵")

        # 샘플 공고 생성
        sample_jobs = self._make_sample_jobs(final_jobs[:5])

        return {
            "jobs": final_jobs,
            "sample_jobs": sample_jobs,
            "location_filtered": location_filtered,
            "location_info": location_info,
            "job_types_parsed": job_types
        }

    def _get_location_coordinates(self, location: str) -> Optional[tuple]:
        """
        위치명에서 좌표 추출 (지하철역/구/동 기반)
        """
        if not location:
            return None

        # SeoulSubwayCommute의 _parse_location 활용
        if subway_service.is_available() and subway_service._commute:
            coords = subway_service._commute._parse_location(location)
            if coords:
                return coords

        return None

    def _filter_by_proximity(
        self,
        jobs: List[Dict],
        reference_coords: tuple,
        radius_km: float
    ) -> List[Dict]:
        """
        반경 기반 필터링 (Haversine 공식)
        """
        import math

        def haversine_distance(lat1, lon1, lat2, lon2):
            """두 좌표 간 거리 (km)"""
            R = 6371  # 지구 반지름 (km)
            phi1, phi2 = math.radians(lat1), math.radians(lat2)
            delta_phi = math.radians(lat2 - lat1)
            delta_lambda = math.radians(lon2 - lon1)

            a = math.sin(delta_phi/2)**2 + \
                math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

            return R * c

        ref_lat, ref_lng = reference_coords
        results = []

        for job in jobs:
            job_coords = self._get_job_coordinates(job)
            if not job_coords:
                continue

            distance = haversine_distance(ref_lat, ref_lng, job_coords[0], job_coords[1])

            if distance <= radius_km:
                job_copy = dict(job)
                job_copy['distance_km'] = round(distance, 1)
                job_copy['distance_text'] = f"약 {round(distance, 1)}km"
                results.append(job_copy)

        # 거리순 정렬
        results.sort(key=lambda x: x.get('distance_km', 999))
        return results

    def _get_job_coordinates(self, job: Dict) -> Optional[tuple]:
        """
        공고에서 좌표 추출
        """
        # 직접 좌표가 있으면 사용
        if job.get("lat") and job.get("lng"):
            try:
                return (float(job["lat"]), float(job["lng"]))
            except (ValueError, TypeError):
                pass

        # location_full에서 좌표 추출 (지하철역/구 기반)
        location = job.get("location_full") or job.get("location", "")
        if location and subway_service.is_available() and subway_service._commute:
            return subway_service._commute._parse_location(location)

        return None

    async def _parse_job_types(self, job_type_query: str) -> List[str]:
        """
        직무 쿼리에서 검색할 직무 목록 추출 (맥락 이해 AI 파싱)

        - 명확히 다른 직무 OR 연결 → 분리
        - 같은 분야 세부 조건 → 통합

        Args:
            job_type_query: 사용자 직무 표현 원문

        Returns:
            직무 목록
        """
        if not job_type_query:
            return []

        prompt = PARSE_JOB_TYPES_PROMPT.format(job_type_query=job_type_query)

        try:
            response = self.filter_model.generate_content(prompt)
            response_text = response.text.strip()

            # JSON 배열 파싱
            match = re.search(r'\[([^\]]*)\]', response_text, re.DOTALL)
            if match:
                array_str = "[" + match.group(1) + "]"
                job_types = json.loads(array_str)
                result = [jt for jt in job_types if isinstance(jt, str) and jt.strip()]
                logger.info(f"직무 파싱: '{job_type_query}' → {result}")
                return result

        except Exception as e:
            logger.error(f"직무 파싱 오류: {e}")

        # 파싱 실패 시 원문 그대로 사용
        return [job_type_query]

    async def _filter_by_job_type(
        self,
        job_type: str,
        jobs: List[Dict]
    ) -> List[Dict]:
        """Stage 1: AI가 직무 유형으로 공고 필터링 (배치 처리 지원)"""
        if not job_type or not jobs:
            return jobs

        # 배치 크기: 500건씩 처리
        BATCH_SIZE = 500
        all_selected_ids = []

        # 배치 처리
        for batch_start in range(0, len(jobs), BATCH_SIZE):
            batch_jobs = jobs[batch_start:batch_start + BATCH_SIZE]

            # 후보 목록 포맷팅
            candidate_lines = []
            for c in batch_jobs:
                job_id = c.get("id", "")
                title = c.get("title", "")[:50]
                job_type_raw = c.get("job_type_raw", "")[:30]
                candidate_lines.append(f'[{job_id}] {title} ({job_type_raw})')

            candidates_text = "\n".join(candidate_lines)

            prompt = SELECT_JOBS_BY_TYPE_PROMPT.format(
                job_type=job_type,
                candidates=candidates_text
            )

            try:
                response = self.filter_model.generate_content(prompt)
                response_text = response.text.strip()

                # JSON 배열 파싱
                batch_selected_ids = self._parse_id_array(response_text)
                all_selected_ids.extend(batch_selected_ids)

                logger.info(f"배치 {batch_start//BATCH_SIZE + 1}: {len(batch_selected_ids)}건 선별")

            except Exception as e:
                logger.error(f"Stage 1 배치 {batch_start//BATCH_SIZE + 1} 오류: {e}")
                # 오류 발생 시 해당 배치는 건너뜀

        # 선택된 ID로 필터링
        id_to_job = {j["id"]: j for j in jobs}
        selected_jobs = [
            id_to_job[job_id]
            for job_id in all_selected_ids
            if job_id in id_to_job
        ]

        logger.info(f"Stage 1 전체: {len(jobs)}건 중 {len(selected_jobs)}건 선별")

        return selected_jobs

    def _make_sample_jobs(self, jobs: List[Dict]) -> List[Dict]:
        """AI에게 보여줄 샘플 공고 생성"""
        sample = []
        for job in jobs:
            sample.append({
                "id": job.get("id", ""),
                "title": job.get("title", "")[:40],
                "company": job.get("company_name", ""),
                "location": job.get("location_full", "") or job.get("location", ""),
                "salary": job.get("salary_text", "협의"),
                "travel_time": job.get("travel_time_text", "")
            })
        return sample

    def _extract_function_calls(self, response) -> List:
        """응답에서 모든 Function Call 추출"""
        function_calls = []
        for part in response.parts:
            if hasattr(part, "function_call") and part.function_call:
                function_calls.append(part.function_call)
        return function_calls

    def _extract_function_call(self, response):
        """응답에서 첫 번째 Function Call 추출 (하위 호환)"""
        calls = self._extract_function_calls(response)
        return calls[0] if calls else None

    def _parse_id_array(self, text: str) -> List[str]:
        """응답 텍스트에서 ID 배열 추출"""
        match = re.search(r'\[([^\]]*)\]', text, re.DOTALL)
        if match:
            try:
                array_str = "[" + match.group(1) + "]"
                parsed = json.loads(array_str)
                # 문자열만 추출 (dict 등 제외)
                return [item for item in parsed if isinstance(item, str)]
            except json.JSONDecodeError:
                pass
        ids = re.findall(r'["\']([jk_\d]+)["\']', text)
        return ids

    def _extract_text_response(self, response) -> str:
        """응답에서 텍스트 추출"""
        response_text = ""
        for part in response.parts:
            if hasattr(part, "text") and part.text:
                response_text += part.text
        return response_text

    def _empty_pagination(self, page_size: int) -> Dict[str, Any]:
        """빈 페이지네이션 객체"""
        return {
            "page": 1,
            "page_size": page_size,
            "total_count": 0,
            "total_pages": 0,
            "has_next": False,
            "has_prev": False
        }

    def _reconstruct_history(self, serialized: List[Dict]) -> List:
        """
        직렬화된 히스토리를 Gemini Content 형식으로 재구성

        Args:
            serialized: 직렬화된 히스토리

        Returns:
            Gemini Content 객체 리스트
        """
        history = []
        for item in serialized:
            try:
                role = item.get("role", "user")
                parts_data = item.get("parts", [])

                parts = []
                for part_data in parts_data:
                    part_type = part_data.get("type", "text")

                    if part_type == "text":
                        parts.append(genai.protos.Part(text=part_data.get("content", "")))
                    elif part_type == "function_call":
                        parts.append(genai.protos.Part(
                            function_call=genai.protos.FunctionCall(
                                name=part_data.get("name", ""),
                                args=part_data.get("args", {})
                            )
                        ))
                    elif part_type == "function_response":
                        parts.append(genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=part_data.get("name", ""),
                                response=part_data.get("response", {})
                            )
                        ))

                if parts:
                    history.append(genai.protos.Content(role=role, parts=parts))

            except Exception as e:
                logger.warning(f"히스토리 항목 재구성 실패: {e}")
                continue

        return history

    def get_cached_page(
        self,
        conversation_id: str,
        page: int = 1,
        page_size: int = 20
    ) -> Optional[Dict[str, Any]]:
        """
        캐시된 검색 결과에서 페이지 가져오기 (AI 재호출 없음)

        Args:
            conversation_id: 대화 ID
            page: 페이지 번호
            page_size: 페이지당 결과 수

        Returns:
            페이지 결과 또는 None (캐시 없음)
        """
        cache = self._search_cache.get(conversation_id)
        if not cache:
            return None

        jobs = cache.get("jobs", [])
        total_count = len(jobs)
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_jobs = jobs[start_idx:end_idx]

        formatted_jobs = format_job_results(page_jobs)

        return {
            "jobs": formatted_jobs,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            },
            "search_params": cache.get("search_params", {}),
            "success": True
        }


def check_gemini() -> bool:
    """Gemini API 연결 상태 확인"""
    try:
        model = genai.GenerativeModel(settings.GEMINI_MODEL)
        response = model.generate_content("테스트")
        return bool(response.text)
    except Exception:
        return False


# 싱글톤 인스턴스
gemini_service = GeminiService()
