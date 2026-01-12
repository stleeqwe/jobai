"""Gemini API 서비스 모듈"""

import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool
from typing import Any, Dict, List

from app.config import settings
from app.services.job_search import search_jobs_in_db

# API 키 설정
genai.configure(api_key=settings.GEMINI_API_KEY)


def _convert_proto_to_dict(proto_obj) -> Dict[str, Any]:
    """protobuf 객체를 Python dict로 변환"""
    result = {}
    for key, value in proto_obj.items():
        # RepeatedComposite (배열) 처리
        if hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
            try:
                result[key] = list(value)
            except:
                result[key] = value
        else:
            result[key] = value
    return result

# Function Calling 정의
SEARCH_JOBS_FUNCTION = FunctionDeclaration(
    name="search_jobs",
    description="""
    채용공고 데이터베이스에서 조건에 맞는 공고를 검색합니다.
    조건이 없는 필드는 생략하면 해당 조건 없이 검색합니다.
    사용자가 조건을 언급하면 반드시 이 함수를 호출해야 합니다.
    """,
    parameters={
        "type": "object",
        "properties": {
            "job_type": {
                "type": "string",
                "description": "정규화된 직무명 (예: 웹디자이너, 백엔드, 프론트엔드, 마케터, 영업, 데이터분석가)"
            },
            "job_keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "직무 관련 기술/스킬 키워드 (예: React, Python, Figma, AWS)"
            },
            "job_category": {
                "type": "string",
                "enum": ["IT개발", "디자인", "마케팅", "영업", "경영지원", "기획", "서비스", "기타"],
                "description": "직무 대분류"
            },
            "preferred_locations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "선호 지역 (구/시 단위, 예: 강남구, 서초구, 성남시)"
            },
            "user_location": {
                "type": "string",
                "description": "사용자 출발 위치 (동/역 단위, 예: 천호동, 강남역, 홍대입구)"
            },
            "commute_time_minutes": {
                "type": "integer",
                "description": "최대 통근시간 (분 단위)"
            },
            "experience_type": {
                "type": "string",
                "enum": ["신입", "경력", "경력무관"],
                "description": "경력 조건"
            },
            "experience_years_min": {
                "type": "integer",
                "description": "최소 경력 연차 (경력인 경우)"
            },
            "salary_min": {
                "type": "integer",
                "description": "최소 연봉 (만원 단위, 예: 4000 = 4천만원)"
            },
            "employment_type": {
                "type": "string",
                "enum": ["정규직", "계약직", "인턴", "프리랜서", "아르바이트"],
                "description": "고용형태"
            },
            "limit": {
                "type": "integer",
                "description": "검색 결과 최대 개수 (기본값 10)"
            }
        }
    }
)

SYSTEM_PROMPT = """
너는 채용공고 검색을 도와주는 AI 어시스턴트 "잡챗"이야.
사용자가 원하는 채용 조건을 파악해서 search_jobs 함수를 호출해.

## 역할
1. 사용자의 자연어 입력에서 채용 조건을 정확히 추출
2. search_jobs 함수를 호출하여 DB 검색
3. 검색 결과를 친근하고 자연스럽게 소개

## 조건 추출 규칙

### 위치 처리
- "강남 근처" → preferred_locations: ["강남구", "서초구", "송파구"]
- "판교" → preferred_locations: ["성남시"]
- "천호동에서 1시간 이내" → user_location: "천호동", commute_time_minutes: 60
- 위치 언급 없으면 → 조건 없이 전체 검색

### 연봉 처리
- "연봉 4천 이상" → salary_min: 4000
- "5천만원 이상" → salary_min: 5000
- "월 300 이상" → salary_min: 3600 (연봉 환산)
- 연봉 언급 없으면 → 조건 없이 검색

### 경력 처리
- "신입" → experience_type: "신입"
- "3년차", "경력 3년" → experience_type: "경력", experience_years_min: 3
- 경력 언급 없으면 → 조건 없이 검색

### 직무 처리
- 구체적 직무명 사용: 웹디자이너, 백엔드, 프론트엔드, 마케터, 데이터분석가 등
- 기술 스택이 있으면 job_keywords에 추가: React, Python, Figma 등

## 중요 규칙
1. 사용자가 채용공고를 찾는다고 하면 반드시 search_jobs를 호출해
2. 조건이 불명확해도 일단 검색 시도 (조건 없는 필드는 생략)
3. 검색 결과가 없으면 조건 완화를 친절하게 제안
4. 검색 결과가 있으면 간략히 요약하고 주요 공고를 소개

## 응답 스타일
- 존댓말 사용
- 친근하고 자연스럽게
- 결과가 많으면 상위 3~5개만 하이라이트
- 결과가 없으면 대안 제시
"""


class GeminiService:
    """Gemini API 서비스"""

    def __init__(self):
        self.model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            tools=[Tool(function_declarations=[SEARCH_JOBS_FUNCTION])],
            system_instruction=SYSTEM_PROMPT
        )

    async def process_message(self, message: str) -> Dict[str, Any]:
        """
        사용자 메시지를 처리하고 검색 결과와 응답을 반환

        Args:
            message: 사용자 메시지

        Returns:
            {
                "response": AI 응답 텍스트,
                "jobs": 채용공고 리스트,
                "search_params": 검색에 사용된 파라미터,
                "success": 성공 여부
            }
        """
        try:
            # 대화 시작
            chat = self.model.start_chat()

            # 첫 번째 응답 받기
            response = chat.send_message(message)

            jobs = []
            search_params = {}

            # Function Call 처리
            for part in response.parts:
                if hasattr(part, "function_call") and part.function_call:
                    fn = part.function_call

                    # 검색 파라미터 추출 (protobuf 객체를 Python 네이티브 타입으로 변환)
                    if fn.args:
                        search_params = _convert_proto_to_dict(fn.args)
                    else:
                        search_params = {}

                    # DB 검색 실행
                    jobs = await search_jobs_in_db(search_params)

                    # 검색 결과를 모델에 다시 전달
                    response = chat.send_message(
                        genai.protos.Content(
                            parts=[
                                genai.protos.Part(
                                    function_response=genai.protos.FunctionResponse(
                                        name="search_jobs",
                                        response={
                                            "jobs": jobs[:10],
                                            "total_count": len(jobs),
                                            "search_params": search_params
                                        }
                                    )
                                )
                            ]
                        )
                    )

            # 최종 텍스트 응답 추출
            response_text = ""
            for part in response.parts:
                if hasattr(part, "text") and part.text:
                    response_text += part.text

            return {
                "response": response_text,
                "jobs": jobs,
                "search_params": search_params,
                "success": True
            }

        except Exception as e:
            return {
                "response": "죄송합니다. 처리 중 오류가 발생했습니다. 다시 시도해주세요.",
                "jobs": [],
                "search_params": {},
                "success": False,
                "error": str(e)
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
