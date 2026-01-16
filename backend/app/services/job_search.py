"""채용공고 검색 서비스 - V6 (통근시간 기반)

직무 + 연봉 필터링 후 지하철 통근시간 계산 및 필터링
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.db import get_db
from app.models.types import JobDict, FormattedJobDict, SearchResultDict
from app.services.subway import subway_service
from app.utils.filters import matches_salary, matches_company_location
from app.utils.keyword_matcher import calculate_match_score, matches_keywords
from app.utils.commute import calculate_commutes, filter_and_enrich

logger = logging.getLogger(__name__)

# 더미 데이터 경로
DUMMY_JOBS_PATH = Path(__file__).parent.parent / "data" / "dummy_jobs.json"


async def search_jobs_with_commute(
    job_keywords: List[str],
    salary_min: Optional[int] = None,
    commute_origin: str = "",
    commute_max_minutes: Optional[int] = None,
    salary_max: Optional[int] = None,
    company_location: str = "",
) -> SearchResultDict:
    """
    채용공고 검색 (통근시간 필터는 선택적)

    Args:
        job_keywords: 직무 키워드 리스트
        salary_min: 최소 연봉 (만원), 무관이면 0
        commute_origin: 통근 기준점 (사용자 현재 위치)
        commute_max_minutes: 최대 통근시간 (분), None이면 통근시간 계산만 수행
        salary_max: 최대 연봉 (선택)
        company_location: 회사 위치 필터 (예: "강남역", "서초구")

    Returns:
        {
            "jobs": [...],
            "total_count": int,
            "filtered_by_commute": int
        }
    """
    logger.info(f"검색 시작: keywords={job_keywords}, salary={salary_min}+, "
                f"company_loc={company_location}, commute_max={commute_max_minutes}")

    # salary_min이 None이면 0으로 처리 (연봉 무관)
    salary_min_val = salary_min if salary_min is not None else 0

    # 1. DB에서 직무+연봉+회사위치 필터링
    db_jobs = await _filter_from_db(
        job_keywords=job_keywords,
        salary_min=salary_min_val,
        salary_max=salary_max,
        company_location=company_location
    )
    logger.info(f"DB 필터 결과: {len(db_jobs)}건")

    if not db_jobs:
        return {"jobs": [], "total_count": 0, "filtered_by_commute": 0}

    # 2. 사용자 위치가 있으면 항상 통근시간 계산
    if commute_origin:
        jobs_with_commute = await _calculate_commute_times(
            jobs=db_jobs,
            origin=commute_origin,
            max_minutes=commute_max_minutes
        )

        if commute_max_minutes is not None:
            logger.info(f"통근시간 필터 결과: {len(jobs_with_commute)}건")
            # 통근시간순 정렬
            jobs_with_commute.sort(key=lambda x: x.get("commute_minutes", 999))
            return {
                "jobs": jobs_with_commute,
                "total_count": len(jobs_with_commute),
                "filtered_by_commute": len(db_jobs) - len(jobs_with_commute)
            }

        logger.info("통근시간 계산만 수행 - 필터 없음")
        return {
            "jobs": jobs_with_commute,
            "total_count": len(jobs_with_commute),
            "filtered_by_commute": 0
        }

    # 통근 기준점이 없으면 기존 결과 반환
    logger.info("통근 기준점 없음 - DB 결과 그대로 반환")
    return {
        "jobs": db_jobs,
        "total_count": len(db_jobs),
        "filtered_by_commute": 0
    }


async def _filter_from_db(
    job_keywords: List[str],
    salary_min: int,
    salary_max: Optional[int] = None,
    company_location: str = "",
    limit: int = 2000
) -> List[JobDict]:
    """
    DB에서 직무+연봉+회사위치 기준 필터링

    키워드 매칭 방식:
    - title에 키워드 포함 OR
    - job_type_raw에 키워드 포함 OR
    - job_keywords 배열에 키워드 포함

    회사 위치 필터:
    - company_location이 있으면 해당 지역 회사만 필터링
    """
    db = get_db()
    if db is None:
        logger.warning("Firestore 미연결 - 더미 데이터 반환")
        return _get_dummy_jobs()

    try:
        # 기본 쿼리: 활성 공고
        query = db.collection("jobs").where("is_active", "==", True)

        # Firestore는 복잡한 OR 쿼리 제한 → 전체 조회 후 Python 필터
        # (향후 최적화: job_category 인덱스 활용)

        jobs_with_scores = []
        seen = 0
        # 충분한 후보를 확보하기 위해 넉넉하게 조회 (필터링 후 limit 적용)
        async for doc in query.limit(limit * 10).stream():
            job = doc.to_dict()

            # 직무 키워드 매칭
            match_score = calculate_match_score(job, job_keywords)
            if match_score == 0:
                continue

            # 연봉 필터
            if not matches_salary(job, salary_min, salary_max):
                continue

            # 회사 위치 필터
            if company_location and not matches_company_location(job, company_location):
                continue

            jobs_with_scores.append((match_score, seen, job))
            seen += 1

            if len(jobs_with_scores) >= limit:
                break

        # 제목 매칭 우선으로 정렬 (score 내림차순, 입력 순서 유지)
        jobs_with_scores.sort(key=lambda item: (-item[0], item[1]))
        return [job for _, __, job in jobs_with_scores]

    except Exception as e:
        logger.error(f"DB 조회 오류: {e}")
        return []


async def _calculate_commute_times(
    jobs: List[JobDict],
    origin: str,
    max_minutes: Optional[int]
) -> List[JobDict]:
    """
    통근시간 계산 및 (옵션) 필터링

    지하철 모듈 기반:
    1. 출발지 → 가장 가까운 역 (도보)
    2. 역 → 역 (지하철)
    3. 도착역 → 회사 (도보)
    """
    if not subway_service.is_available():
        logger.warning("지하철 서비스 사용 불가 - 필터 없이 반환")
        return jobs

    # 통근시간 계산 (순수 계산, 필터링 없음)
    job_commute_pairs = calculate_commutes(jobs, origin, subway_service)

    # 필터링 및 데이터 보강
    return filter_and_enrich(job_commute_pairs, max_minutes)


def format_job_results(jobs: List[JobDict]) -> List[FormattedJobDict]:
    """API 응답용 포맷팅"""
    results: List[FormattedJobDict] = []

    for job in jobs:
        formatted: FormattedJobDict = {
            "id": job.get("id", ""),
            "company_name": job.get("company_name", ""),
            "title": job.get("title", ""),
            "location": job.get("location_full") or job.get("location_gugun", ""),
            "salary_text": job.get("salary_text", "협의"),
            "experience_type": _format_experience(job),
            "employment_type": job.get("employment_type", ""),
            "deadline": job.get("deadline", ""),
            "url": job.get("url", ""),
            "commute_minutes": job.get("commute_minutes"),
            "commute_text": job.get("commute_text", ""),
        }
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
    from google.cloud import firestore

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


def _get_dummy_jobs() -> List[JobDict]:
    """로컬 테스트용 더미 데이터 (외부 JSON 파일에서 로드)"""
    try:
        with open(DUMMY_JOBS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"더미 데이터 파일을 찾을 수 없습니다: {DUMMY_JOBS_PATH}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"더미 데이터 파싱 오류: {e}")
        return []
