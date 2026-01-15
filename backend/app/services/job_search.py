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
        commute_max_minutes: 최대 통근시간 (분), None이면 통근시간 계산 안 함
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

    # 2. 통근시간 필터가 있을 때만 계산
    if commute_max_minutes is not None and commute_origin:
        jobs_with_commute = await _calculate_commute_times(
            jobs=db_jobs,
            origin=commute_origin,
            max_minutes=commute_max_minutes
        )
        logger.info(f"통근시간 필터 결과: {len(jobs_with_commute)}건")

        # 통근시간순 정렬
        jobs_with_commute.sort(key=lambda x: x.get("commute_minutes", 999))

        return {
            "jobs": jobs_with_commute,
            "total_count": len(jobs_with_commute),
            "filtered_by_commute": len(db_jobs) - len(jobs_with_commute)
        }
    else:
        # 통근시간 필터 없음 - DB 결과 그대로 반환
        logger.info("통근시간 필터 없음 - DB 결과 그대로 반환")
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

        jobs = []
        # 충분한 후보를 확보하기 위해 넉넉하게 조회 (필터링 후 limit 적용)
        async for doc in query.limit(limit * 10).stream():
            job = doc.to_dict()

            # 직무 키워드 매칭
            if not _matches_keywords(job, job_keywords):
                continue

            # 연봉 필터
            if not _matches_salary(job, salary_min, salary_max):
                continue

            # 회사 위치 필터
            if company_location and not _matches_company_location(job, company_location):
                continue

            jobs.append(job)

            if len(jobs) >= limit:
                break

        return jobs

    except Exception as e:
        logger.error(f"DB 조회 오류: {e}")
        return []


def _matches_keywords(job: Dict, keywords: List[str]) -> bool:
    """
    직무 키워드 매칭 (AI 확장 키워드 기반)

    AI가 유사어/동의어를 확장해서 전달하므로 키워드를 통째로 매칭.
    - ["웹디자이너", "UI디자이너", "웹퍼블리셔"] 중 하나라도 매칭되면 True
    - 공백 제거 버전도 함께 매칭 (웹 디자이너 → 웹디자이너)
    """
    if not keywords:
        return True

    # 매칭 대상 텍스트
    title = job.get("title", "").lower()
    job_type_raw = job.get("job_type_raw", "").lower()
    job_keywords_field = [k.lower() for k in job.get("job_keywords", [])]
    search_text = f"{title} {job_type_raw}"
    search_text_no_space = search_text.replace(" ", "")  # 공백 제거 버전

    # 각 키워드를 통째로 매칭 (AI가 이미 확장해줌)
    for keyword in keywords:
        kw = keyword.lower().strip()
        if len(kw) < 2:
            continue

        # 공백 제거 버전도 생성 (웹 디자이너 → 웹디자이너)
        kw_no_space = kw.replace(" ", "")

        # 1. 키워드가 title이나 job_type_raw에 포함되는지 (공백 유무 모두 체크)
        if kw in search_text or kw_no_space in search_text or kw_no_space in search_text_no_space:
            return True

        # 2. job_keywords 필드에 포함되는지
        for jk in job_keywords_field:
            if kw in jk or kw_no_space in jk or jk in kw or jk in kw_no_space:
                return True

    return False


def _matches_salary(job: Dict, salary_min: int, salary_max: Optional[int]) -> bool:
    """연봉 조건 매칭

    정책:
    - salary_min > 0 이면: 명시된 연봉이 있고 조건 충족하는 공고만 (회사내규 제외)
    - salary_min = 0 이면: 모든 공고 포함 (회사내규 포함)
    """
    if salary_min == 0 and salary_max is None:
        return True  # 연봉 무관 - 전부 포함

    job_salary_min = job.get("salary_min")
    job_salary_max = job.get("salary_max")

    # salary_min > 0 인데 공고에 연봉 정보 없으면 (회사내규, 협의) → 제외
    if salary_min > 0 and job_salary_min is None:
        return False

    # 최소 연봉 조건
    if salary_min > 0 and job_salary_min is not None:
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


# 역명 → 구 매핑 (회사 위치 필터용)
STATION_TO_DISTRICT = {
    "강남역": ["강남구", "강남"],
    "역삼역": ["강남구", "역삼"],
    "선릉역": ["강남구", "선릉"],
    "삼성역": ["강남구", "삼성"],
    "서초역": ["서초구", "서초"],
    "교대역": ["서초구", "서초"],
    "잠실역": ["송파구", "잠실"],
    "건대입구역": ["광진구", "광진", "건대"],
    "홍대입구역": ["마포구", "마포", "홍대"],
    "합정역": ["마포구", "마포", "합정"],
    "을지로역": ["중구", "을지로"],
    "광화문역": ["종로구", "종로", "광화문"],
    "판교역": ["판교", "분당"],
    "가산디지털단지역": ["금천구", "가산"],
    "구로디지털단지역": ["구로구", "구로"],
}


def _matches_company_location(job: Dict, company_location: str) -> bool:
    """
    회사 위치 필터링

    company_location이 주어지면 해당 지역에 위치한 회사만 통과

    예:
    - "강남역" → 강남구, 강남 포함된 주소
    - "서초구" → 서초구 포함된 주소
    """
    if not company_location:
        return True

    location_full = (job.get("location_full") or "").lower()
    location_gugun = (job.get("location_gugun") or "").lower()
    search_location = company_location.lower().replace("역", "").replace("근처", "").replace("부근", "").strip()

    # 1. 역명이면 매핑된 구/지역명으로 확장
    search_terms = [search_location]
    for station, districts in STATION_TO_DISTRICT.items():
        station_name = station.replace("역", "").lower()
        if station_name in search_location or search_location in station_name:
            search_terms.extend([d.lower() for d in districts])
            break

    # 2. 구 이름이면 그대로 사용
    if "구" in company_location:
        search_terms.append(search_location)

    # 3. 매칭 확인
    for term in search_terms:
        if term in location_full or term in location_gugun:
            return True

    return False


async def _calculate_commute_times(
    jobs: List[JobDict],
    origin: str,
    max_minutes: int
) -> List[JobDict]:
    """
    통근시간 계산 및 필터링

    지하철 모듈 기반:
    1. 출발지 → 가장 가까운 역 (도보)
    2. 역 → 역 (지하철)
    3. 도착역 → 회사 (도보)
    """
    if not subway_service.is_available():
        logger.warning("지하철 서비스 사용 불가 - 필터 없이 반환")
        # 서비스 불가 시 commute_minutes 없이 반환
        return jobs

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
            job_copy["commute_text"] = commute.get("text", f"{commute_minutes}분")
            job_copy["commute_detail"] = {
                "origin_station": commute.get("origin_station"),
                "dest_station": commute.get("destination_station"),
                "origin_walk": commute.get("origin_walk", 0),
                "dest_walk": commute.get("destination_walk", 0)
            }
            results.append(job_copy)

    return results


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


