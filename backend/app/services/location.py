"""위치/통근시간 처리 모듈"""

from typing import Dict, List, Optional

# 서울 지역 인접 정보
SEOUL_ADJACENCY: Dict[str, List[str]] = {
    "강남구": ["서초구", "송파구", "강동구", "성동구", "용산구"],
    "서초구": ["강남구", "동작구", "관악구", "용산구"],
    "송파구": ["강남구", "강동구", "광진구"],
    "강동구": ["송파구", "강남구", "광진구", "성동구"],
    "마포구": ["서대문구", "용산구", "영등포구", "은평구"],
    "영등포구": ["마포구", "동작구", "구로구", "양천구", "용산구"],
    "용산구": ["마포구", "서초구", "강남구", "성동구", "중구", "영등포구"],
    "성동구": ["강남구", "강동구", "광진구", "동대문구", "중구", "용산구"],
    "광진구": ["송파구", "강동구", "성동구", "동대문구", "중랑구"],
    "종로구": ["중구", "성북구", "서대문구", "은평구", "동대문구"],
    "중구": ["종로구", "성동구", "용산구", "동대문구"],
    "동대문구": ["종로구", "중구", "성동구", "광진구", "중랑구", "성북구"],
    "중랑구": ["동대문구", "광진구", "노원구", "성북구"],
    "성북구": ["종로구", "동대문구", "중랑구", "강북구", "노원구"],
    "강북구": ["성북구", "노원구", "도봉구"],
    "도봉구": ["강북구", "노원구"],
    "노원구": ["도봉구", "강북구", "성북구", "중랑구"],
    "은평구": ["종로구", "서대문구", "마포구"],
    "서대문구": ["종로구", "마포구", "은평구", "중구"],
    "동작구": ["서초구", "영등포구", "관악구", "용산구"],
    "관악구": ["서초구", "동작구", "금천구"],
    "금천구": ["관악구", "구로구", "영등포구"],
    "구로구": ["금천구", "영등포구", "양천구"],
    "양천구": ["구로구", "영등포구", "강서구"],
    "강서구": ["양천구", "영등포구"],
}

# 경기도 주요 도시 인접 (서울 기준)
GYEONGGI_ADJACENT_TO_SEOUL: Dict[str, List[str]] = {
    "고양시": ["은평구", "마포구"],
    "성남시": ["강남구", "송파구"],
    "분당구": ["강남구", "송파구"],
    "하남시": ["강동구", "송파구"],
    "광명시": ["구로구", "금천구"],
    "과천시": ["서초구", "관악구"],
    "부천시": ["구로구", "양천구", "강서구"],
    "안양시": ["관악구", "금천구"],
    "의정부시": ["노원구", "도봉구"],
    "구리시": ["광진구", "중랑구"],
    "남양주시": ["중랑구", "노원구"],
}

# 동별 구 매핑 (주요 동만)
DONG_TO_GU: Dict[str, str] = {
    # 강남권
    "역삼동": "강남구",
    "삼성동": "강남구",
    "논현동": "강남구",
    "대치동": "강남구",
    "청담동": "강남구",
    "신사동": "강남구",
    "압구정동": "강남구",
    "잠실동": "송파구",
    "방이동": "송파구",
    "천호동": "강동구",
    "길동": "강동구",

    # 서초권
    "서초동": "서초구",
    "반포동": "서초구",
    "방배동": "서초구",
    "양재동": "서초구",

    # 마포/영등포권
    "합정동": "마포구",
    "상수동": "마포구",
    "망원동": "마포구",
    "연남동": "마포구",
    "여의도동": "영등포구",
    "문래동": "영등포구",

    # 홍대/신촌권
    "연희동": "서대문구",
    "신촌동": "서대문구",

    # 기타
    "이태원동": "용산구",
    "한남동": "용산구",
    "성수동": "성동구",

    # 역 이름 매핑
    "강남역": "강남구",
    "역삼역": "강남구",
    "삼성역": "강남구",
    "선릉역": "강남구",
    "잠실역": "송파구",
    "홍대입구": "마포구",
    "신촌역": "서대문구",
    "여의도역": "영등포구",
    "신논현역": "강남구",
    "판교역": "성남시",
    "판교": "성남시",
}


def estimate_reachable_locations(user_location: str, commute_minutes: int) -> List[str]:
    """
    사용자 위치와 통근시간을 기반으로 도달 가능한 구/시 목록 추정

    Args:
        user_location: 사용자 위치 (동 또는 구 단위)
        commute_minutes: 최대 통근시간 (분)

    Returns:
        도달 가능한 구/시 리스트
    """
    if not user_location:
        return []

    # 동 → 구 변환
    base_gu = DONG_TO_GU.get(user_location)

    if not base_gu:
        # 이미 구 단위인 경우
        if user_location.endswith("구"):
            base_gu = user_location
        elif user_location.endswith("시"):
            # 경기도 시인 경우
            return _get_gyeonggi_reachable(user_location, commute_minutes)
        else:
            # 알 수 없는 위치 - 서울 전체 반환
            return list(SEOUL_ADJACENCY.keys())

    reachable = {base_gu}

    # 30분 이내: 인접 구
    if commute_minutes >= 30:
        adjacent = SEOUL_ADJACENCY.get(base_gu, [])
        reachable.update(adjacent)

    # 60분 이내: 인접의 인접 + 경기도 인접 도시
    if commute_minutes >= 60:
        for gu in list(reachable):
            second_adjacent = SEOUL_ADJACENCY.get(gu, [])
            reachable.update(second_adjacent)

        # 경기도 인접 도시 추가
        for city, adjacent_gus in GYEONGGI_ADJACENT_TO_SEOUL.items():
            if base_gu in adjacent_gus:
                reachable.add(city)

    # 90분 이상: 서울 전체 + 주요 경기권
    if commute_minutes >= 90:
        reachable.update(SEOUL_ADJACENCY.keys())
        reachable.update(GYEONGGI_ADJACENT_TO_SEOUL.keys())

    return list(reachable)


def _get_gyeonggi_reachable(city: str, commute_minutes: int) -> List[str]:
    """경기도 도시에서 도달 가능한 지역"""
    reachable = {city}

    # 서울 인접 구 추가
    if city in GYEONGGI_ADJACENT_TO_SEOUL:
        seoul_adjacent = GYEONGGI_ADJACENT_TO_SEOUL[city]
        reachable.update(seoul_adjacent)

        if commute_minutes >= 60:
            # 인접 구의 인접도 추가
            for gu in seoul_adjacent:
                more_adjacent = SEOUL_ADJACENCY.get(gu, [])
                reachable.update(more_adjacent)

    return list(reachable)


def get_gu_from_dong(dong: str) -> Optional[str]:
    """동에서 구 추출"""
    return DONG_TO_GU.get(dong)
