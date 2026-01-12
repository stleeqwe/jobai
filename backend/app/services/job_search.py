"""채용공고 검색 서비스"""

from typing import Any, Dict, List, Optional
from google.cloud import firestore

from app.db import get_db
from app.config import settings
from app.services.location import estimate_reachable_locations


async def search_jobs_in_db(params: Dict[str, Any]) -> List[Dict]:
    """
    Firestore에서 채용공고 검색

    복합 인덱스 없이 작동하도록 단순화:
    - Firestore에서는 is_active 필터만 사용
    - 나머지 필터링은 클라이언트 사이드에서 처리

    Args:
        params: 검색 파라미터 (Gemini에서 추출)

    Returns:
        검색된 채용공고 리스트
    """
    db = get_db()

    # Firestore가 없으면 더미 데이터 반환
    if db is None:
        return _get_dummy_jobs(params)

    # 단순 쿼리: is_active만 필터 (복합 인덱스 불필요)
    query = db.collection("jobs").where("is_active", "==", True)

    # 결과 수 제한
    limit = min(
        params.get("limit", settings.DEFAULT_SEARCH_LIMIT),
        settings.MAX_SEARCH_LIMIT
    )

    # 더 많은 결과를 가져와서 클라이언트에서 필터링
    query = query.limit(200)

    # 클라이언트 사이드 필터 준비
    job_type = params.get("job_type", "")
    job_category = params.get("job_category", "")
    experience_type = params.get("experience_type", "")
    employment_type = params.get("employment_type", "")

    # 위치 필터 준비
    locations_raw = params.get("preferred_locations", [])
    locations = list(locations_raw) if locations_raw else []
    if user_location := params.get("user_location"):
        commute_time = params.get("commute_time_minutes", 60)
        estimated_locations = estimate_reachable_locations(user_location, commute_time)
        locations = list(set(locations + estimated_locations))

    # 쿼리 실행
    results = []

    async for doc in query.stream():
        job = doc.to_dict()

        # 직무 필터 (클라이언트 사이드)
        if job_type:
            job_job_type = job.get("job_type", "")
            job_title = job.get("title", "").lower()
            if job_type.lower() not in job_job_type.lower() and job_type.lower() not in job_title:
                continue

        # 직무 카테고리 필터
        if job_category and job.get("job_category") != job_category:
            continue

        # 위치 필터 (클라이언트 사이드)
        if locations:
            job_location = job.get("location_gugun", "") or job.get("location_full", "")
            if not any(loc in job_location for loc in locations):
                continue

        # 경력 필터 (클라이언트 사이드)
        if experience_type:
            job_exp_type = job.get("experience_type", "경력무관")
            if experience_type == "신입" and job_exp_type not in ["신입", "경력무관"]:
                continue
            elif experience_type == "경력" and job_exp_type not in ["경력", "경력무관"]:
                continue

        # 고용형태 필터
        if employment_type and job.get("employment_type") != employment_type:
            continue

        # 연봉 필터 (클라이언트 사이드)
        if salary_min := params.get("salary_min"):
            job_salary = job.get("salary_min")
            if job_salary is None or job_salary < salary_min:
                continue

        # 경력 연차 필터 (클라이언트 사이드)
        if exp_years_min := params.get("experience_years_min"):
            job_exp_max = job.get("experience_max")
            if job_exp_max is not None and job_exp_max < exp_years_min:
                continue

        # 키워드 필터 (클라이언트 사이드)
        if keywords_raw := params.get("job_keywords"):
            keywords = list(keywords_raw) if keywords_raw else []
            job_keywords = job.get("job_keywords", [])
            job_title = job.get("title", "").lower()
            job_type_raw = job.get("job_type_raw", "").lower()

            matched = any(
                kw.lower() in job_title or
                kw.lower() in job_type_raw or
                kw.lower() in [jk.lower() for jk in job_keywords]
                for kw in keywords
            )
            if not matched:
                continue

        # 결과 포맷팅
        results.append({
            "id": job["id"],
            "company_name": job.get("company_name", ""),
            "title": job.get("title", ""),
            "location": job.get("location_full", ""),
            "salary": job.get("salary_text", "협의"),
            "experience": _format_experience(job),
            "employment_type": job.get("employment_type", ""),
            "deadline": job.get("deadline", ""),
            "url": job.get("url", ""),
        })

        # 목표 개수 도달 시 중단
        if len(results) >= limit:
            break

    return results


def _format_experience(job: dict) -> str:
    """경력 정보 포맷팅"""
    exp_type = job.get("experience_type", "")
    exp_min = job.get("experience_min")
    exp_max = job.get("experience_max")

    if exp_type == "신입":
        return "신입"
    elif exp_type == "경력무관":
        return "경력무관"
    elif exp_type == "경력":
        if exp_min and exp_max:
            return f"경력 {exp_min}~{exp_max}년"
        elif exp_min:
            return f"경력 {exp_min}년 이상"
        return "경력"
    return exp_type or "경력무관"


async def get_job_stats() -> dict:
    """
    채용공고 통계 조회
    """
    db = get_db()

    if db is None:
        return {
            "total_jobs": 0,
            "active_jobs": 0,
            "last_crawl": None,
            "note": "Firestore not connected (local mode)"
        }

    # 전체 공고 수
    total_docs = db.collection("jobs").count()
    total_result = await total_docs.get()
    total_jobs = total_result[0][0].value if total_result else 0

    # 활성 공고 수
    active_docs = db.collection("jobs").where("is_active", "==", True).count()
    active_result = await active_docs.get()
    active_jobs = active_result[0][0].value if active_result else 0

    # 최근 크롤링 로그
    crawl_logs = (
        db.collection("crawl_logs")
        .order_by("started_at", direction=firestore.Query.DESCENDING)
        .limit(1)
    )

    last_crawl = None
    async for log in crawl_logs.stream():
        last_crawl = log.to_dict().get("finished_at")

    return {
        "total_jobs": total_jobs,
        "active_jobs": active_jobs,
        "last_crawl": last_crawl,
    }


def _get_dummy_jobs(params: Dict[str, Any]) -> List[Dict]:
    """로컬 테스트용 더미 데이터"""
    job_type = params.get("job_type", "개발자")
    location = params.get("preferred_locations", ["강남구"])[0] if params.get("preferred_locations") else "서울"

    return [
        {
            "id": "demo_001",
            "company_name": "테크스타트업",
            "title": f"{job_type} 채용 (신입/경력)",
            "location": f"서울 {location}",
            "salary": "4,000~6,000만원",
            "experience": "경력무관",
            "employment_type": "정규직",
            "deadline": "상시채용",
            "url": "https://www.jobkorea.co.kr"
        },
        {
            "id": "demo_002",
            "company_name": "글로벌테크",
            "title": f"시니어 {job_type} 모집",
            "location": f"서울 {location}",
            "salary": "5,500~8,000만원",
            "experience": "경력 3년 이상",
            "employment_type": "정규직",
            "deadline": "2026-02-28",
            "url": "https://www.jobkorea.co.kr"
        },
        {
            "id": "demo_003",
            "company_name": "IT솔루션즈",
            "title": f"{job_type} 신입 채용",
            "location": f"서울 {location}",
            "salary": "3,500~4,500만원",
            "experience": "신입",
            "employment_type": "정규직",
            "deadline": "2026-01-31",
            "url": "https://www.jobkorea.co.kr"
        },
    ]
