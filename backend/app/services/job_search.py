"""채용공고 검색 서비스 - V3 (3-Stage Sequential Filter)"""

import logging
from typing import Any, Dict, List
from google.cloud import firestore

from app.db import get_db
from app.config import settings

logger = logging.getLogger(__name__)


async def get_all_active_jobs() -> List[Dict]:
    """
    전체 활성 공고 조회

    Returns:
        활성 공고 리스트 (원본 데이터)
    """
    db = get_db()

    if db is None:
        logger.warning("Firestore 미연결 - 더미 데이터 반환")
        return _get_dummy_jobs()

    try:
        # 서울 전체 크롤링 대응: 5000건으로 상향
        query = db.collection("jobs").where("is_active", "==", True).limit(5000)

        jobs = []
        async for doc in query.stream():
            job = doc.to_dict()
            jobs.append(job)

        return jobs

    except Exception as e:
        logger.error(f"공고 조회 오류: {e}")
        return []


def filter_by_salary(jobs: List[Dict], salary_min: int) -> List[Dict]:
    """
    Stage 2: 연봉 조건 필터링

    포함 조건:
    - salary_min >= 요청값
    - salary_min IS NULL (회사내규, 협상가능)

    제외 조건:
    - salary_min < 요청값 (명시적으로 낮은 연봉)

    Args:
        jobs: 공고 리스트
        salary_min: 최소 연봉 (만원 단위), 0이면 조건 없음

    Returns:
        연봉 조건 충족 공고 리스트
    """
    if salary_min == 0:
        return jobs

    result = []
    for job in jobs:
        job_salary = job.get("salary_min")

        # NULL이면 포함 (회사내규, 협상가능)
        if job_salary is None:
            result.append(job)
        # 요청 연봉 이상이면 포함
        elif job_salary >= salary_min:
            result.append(job)
        # 그 외 (명시적으로 낮은 연봉)는 제외

    return result


def format_job_results(jobs: List[Dict]) -> List[Dict]:
    """
    공고 결과 포맷팅 (API 응답용)

    Args:
        jobs: 원본 공고 리스트

    Returns:
        포맷팅된 공고 리스트
    """
    results = []

    for job in jobs:
        formatted = {
            "id": job.get("id", ""),
            "company_name": job.get("company_name", ""),
            "title": job.get("title", ""),
            "location": job.get("location_full", "") or job.get("location", ""),
            "salary": job.get("salary_text", "협의"),
            "experience": _format_experience(job),
            "employment_type": job.get("employment_type", ""),
            "deadline": job.get("deadline", ""),
            "url": job.get("url", ""),
        }

        # 이동시간 정보 (Maps API 결과)
        if "travel_time_minutes" in job:
            formatted["travel_time_minutes"] = job["travel_time_minutes"]
            formatted["travel_time_text"] = job.get("travel_time_text", "")

        results.append(formatted)

    return results


def _format_experience(job: Dict) -> str:
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


async def get_job_stats() -> Dict[str, Any]:
    """채용공고 통계 조회"""
    db = get_db()

    if db is None:
        return {
            "total_jobs": 0,
            "active_jobs": 0,
            "last_crawl": None,
            "note": "Firestore not connected"
        }

    try:
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

    except Exception as e:
        logger.error(f"통계 조회 오류: {e}")
        return {
            "total_jobs": 0,
            "active_jobs": 0,
            "last_crawl": None,
            "error": str(e)
        }


def _get_dummy_jobs() -> List[Dict]:
    """로컬 테스트용 더미 데이터"""
    return [
        {
            "id": "demo_001",
            "company_name": "테크스타트업",
            "title": "Flutter 앱 개발자",
            "job_type_raw": "앱개발",
            "location_full": "서울 강남구 역삼동",
            "salary_text": "5,000~7,000만원",
            "salary_min": 5000,
            "experience_type": "경력무관",
            "employment_type": "정규직",
            "deadline": "상시채용",
            "url": "https://www.jobkorea.co.kr",
        },
        {
            "id": "demo_002",
            "company_name": "글로벌테크",
            "title": "React Native 개발자",
            "job_type_raw": "앱개발",
            "location_full": "서울 중구 을지로3가",
            "salary_text": "6,000~8,000만원",
            "salary_min": 6000,
            "experience_type": "경력",
            "experience_min": 3,
            "employment_type": "정규직",
            "deadline": "2026-02-28",
            "url": "https://www.jobkorea.co.kr",
        },
        {
            "id": "demo_003",
            "company_name": "IT솔루션즈",
            "title": "iOS 앱 개발자",
            "job_type_raw": "iOS개발",
            "location_full": "서울 종로구 종로3가",
            "salary_text": "회사 내규에 따름",
            "salary_min": None,
            "experience_type": "경력",
            "experience_min": 2,
            "employment_type": "정규직",
            "deadline": "2026-01-31",
            "url": "https://www.jobkorea.co.kr",
        },
        {
            "id": "demo_004",
            "company_name": "디자인팩토리",
            "title": "UI/UX 디자이너",
            "job_type_raw": "웹디자인",
            "location_full": "서울 마포구 상암동",
            "salary_text": "4,500~6,500만원",
            "salary_min": 4500,
            "experience_type": "경력무관",
            "employment_type": "정규직",
            "deadline": "2026-02-15",
            "url": "https://www.jobkorea.co.kr",
        },
        {
            "id": "demo_005",
            "company_name": "백엔드코리아",
            "title": "Java 백엔드 개발자",
            "job_type_raw": "백엔드개발",
            "location_full": "서울 강남구 삼성동",
            "salary_text": "5,500~8,000만원",
            "salary_min": 5500,
            "experience_type": "경력",
            "experience_min": 3,
            "employment_type": "정규직",
            "deadline": "상시채용",
            "url": "https://www.jobkorea.co.kr",
        },
        {
            "id": "demo_006",
            "company_name": "마케팅허브",
            "title": "퍼포먼스 마케터",
            "job_type_raw": "마케팅",
            "location_full": "서울 서초구 서초동",
            "salary_text": "3,800~5,500만원",
            "salary_min": 3800,
            "experience_type": "신입",
            "employment_type": "정규직",
            "deadline": "상시채용",
            "url": "https://www.jobkorea.co.kr",
        },
    ]


# ========== 하위 호환성을 위한 레거시 함수 ==========

async def filter_jobs_by_conditions(params: Dict[str, Any]) -> List[Dict]:
    """[Deprecated] V2 호환용 - 새 코드에서는 사용하지 마세요"""
    logger.warning("filter_jobs_by_conditions는 deprecated입니다. V3 함수를 사용하세요.")
    return await get_all_active_jobs()


def get_jobs_by_ids(
    candidates: List[Dict],
    selected_ids: List[str],
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    """[Deprecated] V2 호환용 - 새 코드에서는 사용하지 마세요"""
    logger.warning("get_jobs_by_ids는 deprecated입니다. V3 함수를 사용하세요.")

    id_to_candidate = {c["id"]: c for c in candidates}
    selected_jobs = [
        id_to_candidate[id]
        for id in selected_ids
        if id in id_to_candidate
    ]

    total_count = len(selected_jobs)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_jobs = selected_jobs[start_idx:end_idx]

    return {
        "jobs": format_job_results(page_jobs),
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }
    }
