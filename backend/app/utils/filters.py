"""
Job filtering utilities - shared between job_search and gemini services

중복 제거를 위해 통합된 필터링 로직
"""
import re
from typing import Dict, Optional


def matches_salary(job: Dict, salary_min: int, salary_max: Optional[int]) -> bool:
    """연봉 조건 매칭

    정책:
    - salary_min > 0 이면: 명시된 연봉이 있고 조건 충족하는 공고만 (회사내규 제외)
    - salary_min = 0 이면: 모든 공고 포함 (회사내규 포함)

    Args:
        job: 공고 딕셔너리 (salary_min, salary_max 필드 포함)
        salary_min: 최소 연봉 (만원), 0이면 무관
        salary_max: 최대 연봉 (만원), None이면 제한 없음

    Returns:
        조건 충족 여부
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


# 역명 → 구/지역 매핑 (회사 위치 필터용)
STATION_TO_DISTRICT = {
    # 강남구
    "강남역": ["강남구", "강남"],
    "역삼역": ["강남구", "역삼"],
    "선릉역": ["강남구", "선릉"],
    "삼성역": ["강남구", "삼성"],
    "논현역": ["강남구", "논현"],
    "신논현역": ["강남구", "강남"],
    "압구정역": ["강남구", "압구정"],
    # 서초구
    "서초역": ["서초구", "서초"],
    "교대역": ["서초구", "서초"],
    "양재역": ["서초구", "양재"],
    # 송파구
    "잠실역": ["송파구", "잠실"],
    "석촌역": ["송파구", "석촌"],
    # 강동구
    "천호역": ["강동구", "천호"],
    # 광진구
    "건대입구역": ["광진구", "광진", "건대"],
    # 마포구
    "홍대입구역": ["마포구", "마포", "홍대"],
    "합정역": ["마포구", "마포", "합정"],
    "상수역": ["마포구", "상수"],
    "망원역": ["마포구", "망원"],
    # 영등포구
    "여의도역": ["영등포구", "여의도"],
    "영등포구청역": ["영등포구", "영등포"],
    "당산역": ["영등포구", "당산"],
    # 용산구
    "용산역": ["용산구", "용산"],
    "이태원역": ["용산구", "이태원"],
    # 종로구
    "광화문역": ["종로구", "종로", "광화문"],
    "종각역": ["종로구", "종로"],
    "안국역": ["종로구", "종로", "안국"],
    # 중구
    "을지로역": ["중구", "을지로"],
    "명동역": ["중구", "명동"],
    "충무로역": ["중구", "충무로"],
    "서울역": ["중구", "용산구", "서울역"],
    # 성동구
    "성수역": ["성동구", "성수"],
    "뚝섬역": ["성동구", "성수"],
    "왕십리역": ["성동구", "왕십리"],
    # 금천구/구로구
    "가산디지털단지역": ["금천구", "가산"],
    "구로디지털단지역": ["구로구", "구로"],
    "독산역": ["금천구", "독산"],
    # 기타
    "판교역": ["판교", "분당"],
    "신도림역": ["구로구", "신도림"],
}

# 동/지역 → 구 매핑
DONG_TO_DISTRICT = {
    "성수동": "성동구",
    "성수": "성동구",
    "여의도": "영등포구",
    "여의도동": "영등포구",
    "테헤란로": "강남구",
    "삼성동": "강남구",
    "역삼동": "강남구",
    "논현동": "강남구",
    "신사동": "강남구",
    "청담동": "강남구",
    "서초동": "서초구",
    "반포동": "서초구",
    "잠실동": "송파구",
    "문정동": "송파구",
    "가산동": "금천구",
    "구로동": "구로구",
    "홍대": "마포구",
    "망원동": "마포구",
    "합정동": "마포구",
    "상암동": "마포구",
    "이태원동": "용산구",
}


def matches_company_location(job: Dict, company_location: str) -> bool:
    """
    회사 위치 필터링

    company_location이 주어지면 해당 지역에 위치한 회사만 통과

    지원 형식:
    - 역명: "강남역", "서울역 부근" → 해당 역 인근 구/지역
    - 구명: "강남구", "서초구" → 해당 구
    - 동명: "성수동", "여의도" → 해당 동/구
    """
    if not company_location:
        return True

    location_full = (job.get("location_full") or "").lower()
    location_gugun = (job.get("location_gugun") or "").lower()

    # 정규화: 부근/근처 제거, 끝의 "역"만 제거 (역삼 → 역삼 유지)
    cleaned = company_location.lower().strip()
    cleaned = re.sub(r'(근처|부근|인근|주변)$', '', cleaned).strip()

    search_terms = []

    # 1. 역명 확인 (끝이 "역"이거나 STATION_TO_DISTRICT에 있음)
    station_key = cleaned if cleaned.endswith("역") else cleaned + "역"
    if station_key in [s.lower() for s in STATION_TO_DISTRICT.keys()]:
        # 정확한 키 찾기
        for station, districts in STATION_TO_DISTRICT.items():
            if station.lower() == station_key:
                search_terms.extend([d.lower() for d in districts])
                break
    # "역" 없이 입력된 경우도 체크 (강남 → 강남역)
    elif not cleaned.endswith("역"):
        for station, districts in STATION_TO_DISTRICT.items():
            station_base = station.replace("역", "").lower()
            if station_base == cleaned:
                search_terms.extend([d.lower() for d in districts])
                break

    # 2. 동/지역명 확인
    if not search_terms:
        for dong, gu in DONG_TO_DISTRICT.items():
            if dong.lower() in cleaned or cleaned in dong.lower():
                search_terms.append(gu.lower())
                search_terms.append(dong.lower())
                break

    # 3. 구 이름 확인
    if "구" in cleaned:
        search_terms.append(cleaned)

    # 4. 폴백: 원본 텍스트 그대로 사용
    if not search_terms:
        search_terms.append(cleaned)

    # 매칭 확인
    for term in search_terms:
        if term in location_full or term in location_gugun:
            return True

    return False
