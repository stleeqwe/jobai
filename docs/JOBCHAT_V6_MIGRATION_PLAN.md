# JobChat V6 마이그레이션 계획서

## 개요

V4(파라미터 추출기)에서 V6(Simple Agentic)로 아키텍처 전환.
LLM을 자율적 판단자로 활용하고, 기존 지하철 모듈 기반 통근시간 계산 유지.

---

## 1. 핵심 아키텍처 변경

### 1.1 V4 (현재) vs V6 (목표)

```
V4 (제거):
입력 → Function Call 강제 → 파라미터 4개 추출 → 고정 파이프라인 → 결과
     (LLM은 파서 역할만)

V6 (목표):
입력 → LLM 자율 판단 → 정보 부족시 질문 / 충분시 검색 도구 호출 → 결과
     (LLM이 전체 판단)
```

### 1.2 V6 핵심 원칙

1. **필수 정보 3가지**: 직무, 연봉, 지역(통근 기준점)
2. **LLM 자율성**: 언제 질문하고, 언제 검색할지 LLM이 결정
3. **검색 결과 직접 전달**: LLM이 50건을 직접 보고 응답 생성
4. **후속 대화 자연 처리**: 필터링, 질문, 정렬 등 LLM이 판단
5. **통근시간**: 지하철 모듈 기반 (비용 $0)

### 1.3 비용 목표

- LLM: ~$9/월 (50건 × 80토큰)
- Maps API: $0 (지하철 모듈 사용)
- 지오코딩: $0 (Kakao 무료 티어)

---

## 2. 파일 변경 계획

### 2.1 변경 대상

```
backend/app/services/
├── gemini.py              # 전면 재작성
├── job_search.py          # 전면 재작성  
├── seoul_subway_commute.py # 유지 (변경 없음)
├── subway.py              # 유지 (변경 없음)
├── geocoding.py           # 유지 (변경 없음)
├── maps.py                # 삭제
└── location.py            # 삭제

crawler/app/scrapers/
└── jobkorea.py            # nearest_station 필드 추가

scripts/
└── migrate_nearest_station.py  # 신규 - 기존 데이터 마이그레이션
```

### 2.2 변경하지 않는 파일

```
backend/app/
├── main.py                # 유지
├── config.py              # 유지
├── db/                    # 유지
├── models/                # 유지
├── routers/               # 유지 (일부 수정)

crawler/                   # 대부분 유지
frontend/                  # 일부 수정
```

---

## 3. 상세 구현 가이드

### 3.1 gemini.py 재작성

#### 3.1.1 새로운 System Prompt

```python
SYSTEM_PROMPT = """
당신은 채용공고 검색 전문가 "잡챗"입니다.

## 당신의 역할
사용자가 원하는 채용공고를 찾아주는 것입니다.
자연스럽게 대화하며 필요한 정보를 수집하고, 적합한 공고를 추천하세요.

## 검색에 필요한 정보 (3가지)
1. **직무**: 어떤 일을 찾는지 (예: 프론트엔드 개발자, 웹디자이너)
2. **연봉**: 희망 연봉 조건 (예: 5000만원 이상, 무관)
3. **통근 기준점**: 출퇴근 기준 위치 (예: 강남역, 집 주소)

## 행동 지침

### 정보가 부족할 때
- 자연스럽게 질문하세요
- 한 번에 너무 많이 묻지 마세요
- 예시를 들어주면 좋습니다

예시:
사용자: "개발자 일자리 찾아줘"
당신: "개발자시군요! 몇 가지만 여쭤볼게요. 
      희망하시는 연봉대가 있으신가요? 없으시면 '무관'이라고 해주셔도 돼요."

### 정보가 충분할 때
- search_jobs 함수를 호출하세요
- 함수 호출 전 "찾아볼게요" 같은 말 하지 마세요
- 바로 호출하세요

### 검색 결과를 받았을 때
- 총 몇 건인지 알려주세요
- 상위 3-5개를 간략히 소개하세요
- 추가 조건이 있는지 물어보세요

예시:
"강남역 기준 40분 이내 프론트엔드 개발자 공고 85건을 찾았어요!

1. 테크스타트업 - React 개발자 (통근 15분)
   연봉 5500~7000만, 강남구 역삼동
   
2. 글로벌테크 - 프론트엔드 (통근 22분)
   연봉 6000~8000만, 서초구 서초동
   
3. ...

혹시 경력 조건이나 회사 규모 선호가 있으신가요?"

### 후속 대화 처리
사용자가 추가 요청을 하면 당신이 판단해서 처리하세요:

- "신입만 볼래" → 현재 결과에서 필터링
- "연봉 높은 순으로" → 현재 결과 정렬
- "더 없어?" → 추가 결과 안내 또는 조건 완화 제안
- "첫 번째 회사 어때?" → 해당 공고 상세 설명
- "판교로 바꿔줘" → 새로 검색 (search_jobs 재호출)

### 응답 스타일
- 존댓말 사용
- 친근하고 자연스럽게
- 간결하게 (장황하지 않게)
- 이모지 사용 자제

## 주의사항
- 모르는 건 모른다고 하세요
- 없는 공고를 만들어내지 마세요
- 검색 결과에 있는 정보만 사용하세요
"""
```

#### 3.1.2 Function Declaration

```python
SEARCH_JOBS_FUNCTION = FunctionDeclaration(
    name="search_jobs",
    description="""
    채용공고를 검색합니다.
    직무, 연봉, 통근 기준점 정보가 모두 있을 때 호출하세요.
    결과는 통근시간 가까운 순으로 정렬되어 반환됩니다.
    """,
    parameters={
        "type": "object",
        "properties": {
            "job_keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "직무 관련 키워드들. 예: ['프론트엔드', 'React', '웹개발']"
            },
            "salary_min": {
                "type": "integer",
                "description": "최소 연봉 (만원 단위). 무관이면 0. 예: 5000"
            },
            "salary_max": {
                "type": "integer",
                "description": "최대 연봉 (만원 단위). 제한 없으면 생략"
            },
            "commute_origin": {
                "type": "string",
                "description": "통근 기준점. 역 이름 또는 주소. 예: '강남역', '서울 마포구 연남동'"
            },
            "commute_max_minutes": {
                "type": "integer",
                "description": "최대 통근시간 (분). 기본값 60. 예: 40"
            }
        },
        "required": ["job_keywords", "salary_min", "commute_origin"]
    }
)
```

#### 3.1.3 GeminiService 클래스 구조

```python
"""Gemini 서비스 - V6 (Simple Agentic)"""

import json
import logging
from typing import Any, Dict, List, Optional
import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool

from app.config import settings
from app.services.job_search import search_jobs_with_commute, format_job_results

logger = logging.getLogger(__name__)
genai.configure(api_key=settings.GEMINI_API_KEY)


class ConversationMemory:
    """세션별 대화 메모리"""
    
    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.last_search_results: List[Dict] = []  # 최대 100건 저장
        self.last_search_params: Dict = {}
        self.displayed_count: int = 0  # 이미 보여준 개수
    
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
        self.displayed_count = end
        return batch
    
    def has_more(self) -> bool:
        """더 보여줄 결과가 있는지"""
        return self.displayed_count < len(self.last_search_results)
    
    def get_remaining_count(self) -> int:
        """남은 결과 수"""
        return len(self.last_search_results) - self.displayed_count


class GeminiService:
    """Gemini 서비스 - V6 Simple Agentic"""
    
    def __init__(self):
        self.model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            tools=[Tool(function_declarations=[SEARCH_JOBS_FUNCTION])],
            system_instruction=SYSTEM_PROMPT
        )
        self._memories: Dict[str, ConversationMemory] = {}
        self._chats: Dict[str, Any] = {}  # Gemini chat sessions
    
    def _get_memory(self, conversation_id: str) -> ConversationMemory:
        if conversation_id not in self._memories:
            self._memories[conversation_id] = ConversationMemory(conversation_id)
        return self._memories[conversation_id]
    
    def _get_chat(self, conversation_id: str):
        if conversation_id not in self._chats:
            self._chats[conversation_id] = self.model.start_chat(history=[])
        return self._chats[conversation_id]
    
    async def process_message(
        self,
        message: str,
        conversation_id: str = "",
    ) -> Dict[str, Any]:
        """
        메시지 처리 - V6 Simple Agentic
        
        LLM이 자율적으로 판단:
        - 정보 부족 → 질문
        - 정보 충분 → search_jobs 호출
        - 후속 요청 → 적절히 처리
        """
        try:
            memory = self._get_memory(conversation_id)
            chat = self._get_chat(conversation_id)
            
            # 메시지 전송
            response = chat.send_message(message)
            
            # Function Call 확인
            function_call = self._extract_function_call(response)
            
            if function_call and function_call.name == "search_jobs":
                # 검색 실행
                params = self._parse_function_args(function_call.args)
                logger.info(f"search_jobs 호출: {params}")
                
                # 검색 수행
                search_result = await search_jobs_with_commute(
                    job_keywords=params.get("job_keywords", []),
                    salary_min=params.get("salary_min", 0),
                    salary_max=params.get("salary_max"),
                    commute_origin=params.get("commute_origin", ""),
                    commute_max_minutes=params.get("commute_max_minutes", 60)
                )
                
                # 메모리에 저장
                memory.save_search(search_result["jobs"], params)
                
                # 첫 50건만 LLM에 전달
                first_batch = memory.get_next_batch(50)
                jobs_for_llm = self._format_jobs_for_llm(first_batch)
                
                # 검색 결과를 LLM에 전달
                result_response = chat.send_message(
                    genai.protos.Content(parts=[
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name="search_jobs",
                                response={
                                    "total_count": search_result["total_count"],
                                    "returned_count": len(first_batch),
                                    "has_more": memory.has_more(),
                                    "jobs": jobs_for_llm
                                }
                            )
                        )
                    ])
                )
                
                response_text = self._extract_text(result_response)
                
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
            
            else:
                # Function Call 없음 - 텍스트 응답
                response_text = self._extract_text(response)
                
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
            line = (
                f"{i}. [{job.get('id', '')}] {job.get('company_name', '')} - {job.get('title', '')}\n"
                f"   통근 {job.get('commute_minutes', '?')}분 | "
                f"{job.get('location_gugun', '')} | "
                f"연봉 {job.get('salary_text', '협의')} | "
                f"{job.get('experience_type', '')}"
            )
            lines.append(line)
        return lines
    
    def _extract_function_call(self, response):
        """응답에서 Function Call 추출"""
        for part in response.parts:
            if hasattr(part, "function_call") and part.function_call:
                return part.function_call
        return None
    
    def _parse_function_args(self, args) -> Dict:
        """Function Call 인자 파싱"""
        result = {}
        for key, value in args.items():
            if hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
                try:
                    result[key] = list(value)
                except:
                    result[key] = value
            else:
                result[key] = value
        return result
    
    def _extract_text(self, response) -> str:
        """응답에서 텍스트 추출"""
        texts = []
        for part in response.parts:
            if hasattr(part, "text") and part.text:
                texts.append(part.text)
        return "".join(texts)


# 싱글톤
gemini_service = GeminiService()
```

---

### 3.2 job_search.py 재작성

```python
"""채용공고 검색 서비스 - V6 (통근시간 기반)"""

import logging
from typing import Any, Dict, List, Optional

from app.db import get_db
from app.services.subway import subway_service
from app.services.geocoding import geocode_address

logger = logging.getLogger(__name__)


async def search_jobs_with_commute(
    job_keywords: List[str],
    salary_min: int,
    commute_origin: str,
    commute_max_minutes: int = 60,
    salary_max: Optional[int] = None,
) -> Dict[str, Any]:
    """
    통근시간 기반 채용공고 검색
    
    Args:
        job_keywords: 직무 키워드 리스트
        salary_min: 최소 연봉 (만원), 무관이면 0
        commute_origin: 통근 기준점 (역명 또는 주소)
        commute_max_minutes: 최대 통근시간 (분)
        salary_max: 최대 연봉 (선택)
    
    Returns:
        {
            "jobs": [...],  # 통근시간순 정렬
            "total_count": int,
            "filtered_by_commute": int
        }
    """
    logger.info(f"검색 시작: keywords={job_keywords}, salary={salary_min}+, origin={commute_origin}")
    
    # 1. DB에서 직무+연봉 필터링
    db_jobs = await _filter_from_db(
        job_keywords=job_keywords,
        salary_min=salary_min,
        salary_max=salary_max
    )
    logger.info(f"DB 필터 결과: {len(db_jobs)}건")
    
    if not db_jobs:
        return {"jobs": [], "total_count": 0, "filtered_by_commute": 0}
    
    # 2. 통근시간 계산 및 필터링
    jobs_with_commute = await _calculate_commute_times(
        jobs=db_jobs,
        origin=commute_origin,
        max_minutes=commute_max_minutes
    )
    logger.info(f"통근시간 필터 결과: {len(jobs_with_commute)}건")
    
    # 3. 통근시간순 정렬
    jobs_with_commute.sort(key=lambda x: x.get("commute_minutes", 999))
    
    return {
        "jobs": jobs_with_commute,
        "total_count": len(jobs_with_commute),
        "filtered_by_commute": len(db_jobs) - len(jobs_with_commute)
    }


async def _filter_from_db(
    job_keywords: List[str],
    salary_min: int,
    salary_max: Optional[int] = None,
    limit: int = 2000
) -> List[Dict]:
    """
    DB에서 직무+연봉 기준 필터링
    
    키워드 매칭 방식:
    - title에 키워드 포함 OR
    - job_type_raw에 키워드 포함 OR
    - job_keywords 배열에 키워드 포함
    """
    db = get_db()
    if db is None:
        logger.warning("Firestore 미연결")
        return []
    
    try:
        # 기본 쿼리: 활성 공고
        query = db.collection("jobs").where("is_active", "==", True)
        
        # Firestore는 복잡한 OR 쿼리 제한 → 전체 조회 후 Python 필터
        # (향후 최적화: job_category 인덱스 활용)
        
        jobs = []
        async for doc in query.limit(limit * 3).stream():  # 여유있게 조회
            job = doc.to_dict()
            
            # 직무 키워드 매칭
            if not _matches_keywords(job, job_keywords):
                continue
            
            # 연봉 필터
            if not _matches_salary(job, salary_min, salary_max):
                continue
            
            jobs.append(job)
            
            if len(jobs) >= limit:
                break
        
        return jobs
    
    except Exception as e:
        logger.error(f"DB 조회 오류: {e}")
        return []


def _matches_keywords(job: Dict, keywords: List[str]) -> bool:
    """직무 키워드 매칭"""
    if not keywords:
        return True
    
    # 매칭 대상 텍스트
    title = job.get("title", "").lower()
    job_type_raw = job.get("job_type_raw", "").lower()
    job_keywords_field = [k.lower() for k in job.get("job_keywords", [])]
    
    # 하나라도 매칭되면 True
    for keyword in keywords:
        kw = keyword.lower()
        if kw in title or kw in job_type_raw:
            return True
        if any(kw in jk for jk in job_keywords_field):
            return True
    
    return False


def _matches_salary(job: Dict, salary_min: int, salary_max: Optional[int]) -> bool:
    """연봉 조건 매칭"""
    if salary_min == 0 and salary_max is None:
        return True  # 연봉 무관
    
    job_salary_min = job.get("salary_min")
    job_salary_max = job.get("salary_max")
    
    # salary_min이 None이면 (회사내규, 협의) 포함
    if job_salary_min is None:
        return True
    
    # 최소 연봉 조건
    if salary_min > 0:
        # 공고의 최대 연봉이 요구 최소보다 낮으면 제외
        if job_salary_max and job_salary_max < salary_min:
            return False
        # 공고의 최소 연봉만 있으면 그걸로 비교
        if job_salary_min < salary_min:
            # 최대 연봉이 없으면 최소 연봉으로 판단
            if not job_salary_max:
                return False
    
    # 최대 연봉 조건 (선택)
    if salary_max:
        if job_salary_min and job_salary_min > salary_max:
            return False
    
    return True


async def _calculate_commute_times(
    jobs: List[Dict],
    origin: str,
    max_minutes: int
) -> List[Dict]:
    """
    통근시간 계산 및 필터링
    
    지하철 모듈 기반:
    1. 출발지 → 가장 가까운 역 (도보)
    2. 역 → 역 (지하철)
    3. 도착역 → 회사 (도보)
    """
    if not subway_service.is_available():
        logger.warning("지하철 서비스 사용 불가")
        return jobs  # 필터 없이 반환
    
    results = []
    
    for job in jobs:
        # 공고 위치 정보
        job_location = job.get("location_full") or job.get("location_gugun", "")
        
        if not job_location:
            continue
        
        # 통근시간 계산
        commute = subway_service.calculate(origin, job_location)
        
        if commute is None:
            # 계산 실패 → 제외 (또는 포함하고 "시간 미상"으로 처리)
            continue
        
        commute_minutes = commute.get("minutes", 999)
        
        # 최대 시간 필터
        if commute_minutes <= max_minutes:
            job_copy = dict(job)
            job_copy["commute_minutes"] = commute_minutes
            job_copy["commute_text"] = commute.get("text", f"약 {commute_minutes}분")
            job_copy["commute_detail"] = {
                "origin_station": commute.get("origin_station"),
                "dest_station": commute.get("destination_station"),
                "origin_walk": commute.get("origin_walk", 0),
                "dest_walk": commute.get("destination_walk", 0)
            }
            results.append(job_copy)
    
    return results


def format_job_results(jobs: List[Dict]) -> List[Dict]:
    """API 응답용 포맷팅"""
    results = []
    
    for job in jobs:
        formatted = {
            "id": job.get("id", ""),
            "company_name": job.get("company_name", ""),
            "title": job.get("title", ""),
            "location": job.get("location_full") or job.get("location_gugun", ""),
            "salary_text": job.get("salary_text", "협의"),
            "experience_type": job.get("experience_type", ""),
            "employment_type": job.get("employment_type", ""),
            "deadline": job.get("deadline", ""),
            "url": job.get("url", ""),
            "commute_minutes": job.get("commute_minutes"),
            "commute_text": job.get("commute_text", ""),
        }
        results.append(formatted)
    
    return results
```

---

### 3.3 subway.py 수정 (래퍼)

기존 subway.py의 `subway_service` 래퍼가 `calculate` 메서드를 제대로 노출하는지 확인.
필요시 아래처럼 수정:

```python
"""지하철 서비스 래퍼 - V6"""

from app.services.seoul_subway_commute import SeoulSubwayCommute

class SubwayService:
    """지하철 통근시간 계산 서비스"""
    
    def __init__(self):
        self._commute = SeoulSubwayCommute()
    
    def is_available(self) -> bool:
        return self._commute.is_initialized()
    
    def calculate(self, origin: str, destination: str):
        """
        통근시간 계산
        
        Args:
            origin: 출발지 (역명, 주소, "lat,lng")
            destination: 도착지 (역명, 주소, "lat,lng")
        
        Returns:
            {
                "minutes": int,
                "text": "약 30분",
                "origin_station": str,
                "destination_station": str,
                "origin_walk": int,
                "destination_walk": int
            }
        """
        return self._commute.calculate(origin, destination)
    
    def filter_jobs(self, jobs, origin: str, max_minutes: int):
        """공고 필터링 (하위 호환)"""
        return self._commute.filter_jobs(jobs, origin, max_minutes)


# 싱글톤
subway_service = SubwayService()
```

---

### 3.4 크롤러 수정 - nearest_station 필드 추가

`crawler/app/scrapers/jobkorea.py`의 `_fetch_detail_info` 메서드 마지막에 추가:

```python
# 기존 코드 끝에 추가

# 12. 가장 가까운 지하철역 계산
nearest_station = ""
station_walk_minutes = None

if company_address:
    from app.services.seoul_subway_commute import SeoulSubwayCommute
    
    try:
        subway = SeoulSubwayCommute()
        coords = subway._parse_location(company_address)
        
        if coords:
            station_id, walk_minutes = subway._find_nearest_station(coords[0], coords[1])
            if station_id:
                station_info = subway.stations.get(station_id, {})
                nearest_station = station_info.get("name", "")
                station_walk_minutes = walk_minutes
    except Exception as e:
        logger.debug(f"지하철역 계산 실패: {e}")

return {
    # ... 기존 필드들 ...
    
    # 신규 필드
    "nearest_station": nearest_station,
    "station_walk_minutes": station_walk_minutes,
}
```

**주의**: 크롤러에서 `seoul_subway_commute.py`를 import하려면 해당 파일을 crawler 디렉토리에도 복사하거나, 공통 모듈로 분리해야 함.

---

### 3.5 기존 데이터 마이그레이션 스크립트

`scripts/migrate_nearest_station.py` 신규 생성:

```python
"""
기존 채용공고 데이터에 nearest_station 필드 추가
"""

import asyncio
import sys
sys.path.append(".")

from google.cloud import firestore
from app.db import get_db
from app.services.seoul_subway_commute import SeoulSubwayCommute


async def migrate():
    db = get_db()
    subway = SeoulSubwayCommute()
    
    print("마이그레이션 시작...")
    
    # 활성 공고 조회
    query = db.collection("jobs").where("is_active", "==", True)
    
    updated = 0
    failed = 0
    skipped = 0
    
    batch = db.batch()
    batch_count = 0
    
    async for doc in query.stream():
        job = doc.to_dict()
        job_id = job.get("id")
        
        # 이미 있으면 스킵
        if job.get("nearest_station"):
            skipped += 1
            continue
        
        # 위치 정보
        location = job.get("location_full") or job.get("company_address") or ""
        
        if not location:
            failed += 1
            continue
        
        # 좌표 파싱
        coords = subway._parse_location(location)
        
        if not coords:
            failed += 1
            continue
        
        # 가장 가까운 역 찾기
        station_id, walk_minutes = subway._find_nearest_station(coords[0], coords[1])
        
        if not station_id:
            failed += 1
            continue
        
        station_info = subway.stations.get(station_id, {})
        nearest_station = station_info.get("name", "")
        
        # 업데이트
        doc_ref = db.collection("jobs").document(doc.id)
        batch.update(doc_ref, {
            "nearest_station": nearest_station,
            "station_walk_minutes": walk_minutes
        })
        
        batch_count += 1
        updated += 1
        
        # 500건마다 커밋
        if batch_count >= 500:
            batch.commit()
            print(f"  {updated}건 업데이트...")
            batch = db.batch()
            batch_count = 0
    
    # 남은 배치 커밋
    if batch_count > 0:
        batch.commit()
    
    print(f"\n완료!")
    print(f"  업데이트: {updated}건")
    print(f"  스킵: {skipped}건")
    print(f"  실패: {failed}건")


if __name__ == "__main__":
    asyncio.run(migrate())
```

---

### 3.6 API 라우터 수정

`backend/app/routers/chat.py` 수정:

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.services.gemini import gemini_service

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = ""


class ChatResponse(BaseModel):
    response: str
    jobs: List[Dict[str, Any]]
    pagination: Optional[Dict[str, Any]]
    success: bool
    error: Optional[str] = None


class MoreResultsRequest(BaseModel):
    conversation_id: str


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """채팅 메시지 처리"""
    result = await gemini_service.process_message(
        message=request.message,
        conversation_id=request.conversation_id
    )
    return ChatResponse(**result)


@router.post("/chat/more", response_model=ChatResponse)
async def more_results(request: MoreResultsRequest):
    """더보기 - 추가 결과 반환"""
    result = await gemini_service.get_more_results(
        conversation_id=request.conversation_id
    )
    return ChatResponse(**result)
```

---

### 3.7 삭제할 파일

```bash
# 삭제 대상
rm backend/app/services/maps.py
rm backend/app/services/location.py

# 확인 후 삭제 (사용 여부 체크)
# grep -r "from app.services.maps" backend/
# grep -r "from app.services.location" backend/
```

---

## 4. 프론트엔드 수정

### 4.1 더보기 버튼 추가

`frontend/src/components/ChatMessage.tsx` 또는 해당 컴포넌트에:

```typescript
interface JobListProps {
  jobs: Job[];
  pagination?: {
    total_count: number;
    displayed: number;
    has_more: boolean;
    remaining: number;
  };
  onLoadMore?: () => void;
}

function JobList({ jobs, pagination, onLoadMore }: JobListProps) {
  return (
    <div>
      {/* 기존 job 목록 렌더링 */}
      {jobs.map(job => (
        <JobCard key={job.id} job={job} />
      ))}
      
      {/* 더보기 버튼 */}
      {pagination?.has_more && (
        <button 
          onClick={onLoadMore}
          className="w-full py-2 mt-4 text-blue-600 border border-blue-600 rounded hover:bg-blue-50"
        >
          더보기 ({pagination.remaining}건 남음)
        </button>
      )}
    </div>
  );
}
```

### 4.2 API 호출 수정

```typescript
// api.ts

export async function sendMessage(message: string, conversationId: string) {
  const response = await fetch(`${API_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_id: conversationId })
  });
  return response.json();
}

export async function loadMoreResults(conversationId: string) {
  const response = await fetch(`${API_URL}/chat/more`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId })
  });
  return response.json();
}
```

---

## 5. CLAUDE.md 업데이트

기존 CLAUDE.md의 V4 관련 내용 제거하고 V6으로 업데이트:

```markdown
## 아키텍처 V6 (Simple Agentic)

### 핵심 철학
- LLM을 파라미터 추출기가 아닌 **자율적 판단자**로 활용
- 필수 정보(직무, 연봉, 통근 기준점)만 수집하면 LLM이 알아서 처리
- 통근시간은 지하철 모듈 기반 (비용 $0)

### 흐름
```
사용자 입력
    │
    ▼
[LLM 자율 판단]
    │
    ├─ 정보 부족 → 자연스럽게 질문
    │
    └─ 정보 충분 → search_jobs 호출
                        │
                        ▼
                [DB 필터] 직무 + 연봉
                        │
                        ▼
                [지하철 모듈] 통근시간 계산 + 필터
                        │
                        ▼
                [상위 100건] → 메모리 저장
                        │
                        ▼
                [50건] → LLM에 전달 → 응답 생성
```

### 파일 구조
- `gemini.py`: LLM 서비스 (Simple Agentic)
- `job_search.py`: 검색 + 통근시간 필터
- `seoul_subway_commute.py`: 지하철 통근시간 계산
- `subway.py`: 지하철 서비스 래퍼

### 비용
- LLM: ~$9/월 (일 1,000명)
- 지도 API: $0 (지하철 모듈)
```

---

## 6. 테스트 시나리오

### 6.1 기본 검색

```
입력: "강남역에서 40분 이내 프론트엔드 개발자 연봉 5천 이상"
기대: 바로 검색 실행, 결과 반환
```

### 6.2 정보 부족

```
입력: "개발자 일자리"
기대: 연봉, 지역 질문
```

### 6.3 후속 필터링

```
[검색 후]
입력: "신입만 볼래"
기대: 기존 결과에서 필터링
```

### 6.4 더보기

```
[50건 표시 후 더보기 클릭]
기대: 나머지 50건 반환 (LLM 호출 없음)
```

### 6.5 조건 변경

```
[강남 검색 후]
입력: "판교로 바꿔줘"
기대: 새로 검색 실행
```

---

## 7. 구현 순서

### Day 1: 백엔드 핵심
1. [ ] `gemini.py` 재작성
2. [ ] `job_search.py` 재작성
3. [ ] `subway.py` 확인/수정
4. [ ] 불필요 파일 삭제 (`maps.py`, `location.py`)

### Day 2: 데이터 & 크롤러
1. [ ] 마이그레이션 스크립트 작성 및 실행
2. [ ] 크롤러 `nearest_station` 필드 추가
3. [ ] API 라우터 수정

### Day 3: 프론트엔드 & 테스트
1. [ ] 더보기 버튼 추가
2. [ ] API 호출 수정
3. [ ] E2E 테스트

### Day 4: 문서화 & 배포
1. [ ] CLAUDE.md 업데이트
2. [ ] 테스트 완료
3. [ ] 배포

---

## 8. 주의사항

### 8.1 기존 데이터 보존
- Firestore 데이터 70,000건 유지
- 마이그레이션 스크립트로 필드 추가만

### 8.2 하위 호환성
- `/chat` API 인터페이스 유지
- 프론트엔드 기존 구조 최대한 유지

### 8.3 롤백 계획
- 기존 `gemini.py` → `gemini_v4.py`로 백업
- 문제 시 import만 변경해서 롤백 가능

---

## 9. 참고 자료

### 9.1 핵심 슬로건
> "우리집에서 출퇴근 40분 이내 웹 디자이너 연봉 4천만원 이상!"

### 9.2 비용 목표
- 월 ~$10 (일 1,000명 기준)
- LLM 토큰만 비용 발생
- 지도 API $0 (지하철 모듈)

### 9.3 정확도 허용 범위
- 통근시간 ±10분 OK
- 40분 요청 → 실제 30~50분 범위 허용
