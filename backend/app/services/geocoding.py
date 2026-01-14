"""
주소 ↔ 좌표 변환 (Geocoding) 모듈

지하철역 좌표 캐시를 우선 사용하고,
필요시 외부 API(Google Maps)를 fallback으로 사용합니다.
"""

import logging
import re
import httpx
from typing import Dict, Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)


# 서울 주요 지역 좌표 캐시 (동/구 중심)
SEOUL_DISTRICTS: Dict[str, Tuple[float, float]] = {
    # 구 중심 좌표
    "강남구": (37.5172, 127.0473),
    "서초구": (37.4837, 127.0324),
    "송파구": (37.5145, 127.1060),
    "강동구": (37.5301, 127.1238),
    "광진구": (37.5384, 127.0823),
    "성동구": (37.5634, 127.0369),
    "동대문구": (37.5744, 127.0396),
    "중랑구": (37.6063, 127.0928),
    "성북구": (37.5894, 127.0167),
    "강북구": (37.6396, 127.0256),
    "도봉구": (37.6688, 127.0471),
    "노원구": (37.6542, 127.0568),
    "은평구": (37.6027, 126.9291),
    "서대문구": (37.5791, 126.9368),
    "마포구": (37.5663, 126.9014),
    "용산구": (37.5324, 126.9906),
    "중구": (37.5641, 126.9979),
    "종로구": (37.5735, 126.9790),
    "영등포구": (37.5264, 126.8963),
    "구로구": (37.4954, 126.8874),
    "금천구": (37.4519, 126.9020),
    "양천구": (37.5170, 126.8665),
    "강서구": (37.5509, 126.8495),
    "동작구": (37.5124, 126.9393),
    "관악구": (37.4784, 126.9516),
}

# 주요 역 주변 랜드마크
LANDMARKS: Dict[str, Tuple[float, float]] = {
    "코엑스": (37.5120, 127.0590),
    "잠실롯데월드타워": (37.5126, 127.1025),
    "여의도": (37.5219, 126.9245),
    "광화문": (37.5759, 126.9769),
    "명동": (37.5636, 126.9869),
    "홍대": (37.5563, 126.9237),
    "신촌": (37.5553, 126.9367),
    "건대": (37.5403, 127.0694),
    "왕십리": (37.5614, 127.0378),
    "가산디지털단지": (37.4816, 126.8827),
    "구로디지털단지": (37.4851, 126.9014),
    "테헤란로": (37.5052, 127.0391),
    "선릉": (37.5046, 127.0492),
    "삼성": (37.5089, 127.0637),
    "청담": (37.5199, 127.0539),
    "압구정": (37.5271, 127.0282),
    "이태원": (37.5345, 126.9944),
    "성수": (37.5445, 127.0559),
    "판교": (37.3947, 127.1112),  # 서울 외곽
}


def parse_coordinates(text: str) -> Optional[Tuple[float, float]]:
    """
    텍스트에서 좌표 파싱

    Args:
        text: "37.497,127.027" 형식 문자열

    Returns:
        (lat, lng) 또는 None
    """
    if "," not in text:
        return None

    try:
        parts = text.split(",")
        lat = float(parts[0].strip())
        lng = float(parts[1].strip())

        # 한국 범위 체크
        if 33 <= lat <= 39 and 124 <= lng <= 132:
            return (lat, lng)
    except (ValueError, IndexError):
        pass

    return None


def geocode_district(location: str) -> Optional[Tuple[float, float]]:
    """
    구/동 이름에서 좌표 반환

    Args:
        location: "강남구", "역삼동" 등

    Returns:
        (lat, lng) 또는 None
    """
    # 구 단위 검색
    for district, coords in SEOUL_DISTRICTS.items():
        if district in location:
            return coords

    # 랜드마크 검색
    for landmark, coords in LANDMARKS.items():
        if landmark in location:
            return coords

    return None


def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """
    주소 → 좌표 변환 (통합)

    우선순위:
    1. 좌표 형식이면 파싱
    2. 구/동/랜드마크 캐시
    3. None (외부 API 필요시 확장)

    Args:
        address: 주소 문자열

    Returns:
        (lat, lng) 또는 None
    """
    if not address:
        return None

    address = address.strip()

    # 1. 좌표 형식
    coords = parse_coordinates(address)
    if coords:
        return coords

    # 2. 구/동/랜드마크
    coords = geocode_district(address)
    if coords:
        return coords

    # 3. 주소에서 구 추출 시도
    # "서울특별시 강남구 역삼동" → "강남구" 추출
    for district in SEOUL_DISTRICTS:
        if district in address:
            return SEOUL_DISTRICTS[district]

    return None


def extract_dong_from_address(address: str) -> Optional[str]:
    """주소에서 동 이름 추출"""
    match = re.search(r'(\w{1,4})동', address)
    if match:
        return match.group(1) + "동"
    return None


def extract_gu_from_address(address: str) -> Optional[str]:
    """주소에서 구 이름 추출"""
    match = re.search(r'(\w{1,3})구', address)
    if match:
        return match.group(1) + "구"
    return None


async def reverse_geocode(lat: float, lng: float) -> Optional[Dict]:
    """
    좌표 → 주소 변환 (역지오코딩)

    Google Maps Geocoding API를 사용하여 좌표를 한국어 주소로 변환합니다.

    Args:
        lat: 위도
        lng: 경도

    Returns:
        {
            "address": "서울특별시 강남구 역삼동",
            "gu": "강남구",
            "dong": "역삼동",
            "full_address": "대한민국 서울특별시 강남구 역삼동 123-45"
        }
        또는 None
    """
    if not settings.GOOGLE_MAPS_API_KEY:
        logger.warning("GOOGLE_MAPS_API_KEY가 설정되지 않음")
        return None

    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "latlng": f"{lat},{lng}",
            "key": settings.GOOGLE_MAPS_API_KEY,
            "language": "ko",
            "result_type": "sublocality_level_2|sublocality_level_1|locality"
        }

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, params=params)
            data = response.json()

        if data.get("status") != "OK" or not data.get("results"):
            logger.warning(f"역지오코딩 실패: {data.get('status')}")
            return None

        result = data["results"][0]
        formatted_address = result.get("formatted_address", "")

        # address_components에서 구/동 추출
        gu = None
        dong = None

        for component in result.get("address_components", []):
            types = component.get("types", [])
            name = component.get("long_name", "")

            # 구 (sublocality_level_1)
            if "sublocality_level_1" in types:
                gu = name
            # 동 (sublocality_level_2)
            elif "sublocality_level_2" in types:
                dong = name

        # 간단한 주소 생성 (구 + 동)
        if gu and dong:
            address = f"{gu} {dong}"
        elif gu:
            address = gu
        elif dong:
            address = dong
        else:
            # fallback: formatted_address에서 추출
            address = formatted_address.replace("대한민국 ", "").replace("서울특별시 ", "")

        return {
            "address": address,
            "gu": gu,
            "dong": dong,
            "full_address": formatted_address
        }

    except Exception as e:
        logger.exception(f"역지오코딩 오류: {e}")
        return None
