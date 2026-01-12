"""지역명 정규화 모듈"""

from typing import Optional

# 시/도 별칭 매핑
SIDO_ALIASES: dict[str, list[str]] = {
    "서울": ["서울", "서울시", "서울특별시"],
    "경기": ["경기", "경기도"],
    "인천": ["인천", "인천시", "인천광역시"],
    "부산": ["부산", "부산시", "부산광역시"],
    "대구": ["대구", "대구시", "대구광역시"],
    "광주": ["광주", "광주시", "광주광역시"],
    "대전": ["대전", "대전시", "대전광역시"],
    "울산": ["울산", "울산시", "울산광역시"],
    "세종": ["세종", "세종시", "세종특별자치시"],
    "강원": ["강원", "강원도", "강원특별자치도"],
    "충북": ["충북", "충청북도"],
    "충남": ["충남", "충청남도"],
    "전북": ["전북", "전라북도", "전북특별자치도"],
    "전남": ["전남", "전라남도"],
    "경북": ["경북", "경상북도"],
    "경남": ["경남", "경상남도"],
    "제주": ["제주", "제주도", "제주특별자치도"],
}

# 서울 구 목록
SEOUL_GU_LIST = [
    "강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구", "금천구",
    "노원구", "도봉구", "동대문구", "동작구", "마포구", "서대문구", "서초구", "성동구",
    "성북구", "송파구", "양천구", "영등포구", "용산구", "은평구", "종로구", "중구", "중랑구"
]

# 경기도 주요 시/군
GYEONGGI_CITY_LIST = [
    "수원시", "성남시", "고양시", "용인시", "부천시", "안산시", "안양시", "남양주시",
    "화성시", "평택시", "의정부시", "시흥시", "파주시", "김포시", "광명시", "광주시",
    "군포시", "하남시", "오산시", "이천시", "안성시", "의왕시", "양평군", "여주시",
    "과천시", "고양시", "구리시", "포천시", "양주시", "동두천시", "가평군", "연천군"
]


def normalize_sido(text: str) -> Optional[str]:
    """
    시/도 이름 정규화

    Args:
        text: 원본 시/도 텍스트

    Returns:
        정규화된 시/도명 (매핑 실패 시 None)
    """
    if not text:
        return None

    text_clean = text.strip()

    for normalized, aliases in SIDO_ALIASES.items():
        for alias in aliases:
            if alias in text_clean:
                return normalized

    return text_clean if text_clean else None


def normalize_location(raw_text: str) -> dict:
    """
    지역 텍스트를 구조화된 데이터로 변환

    Args:
        raw_text: 원본 지역 텍스트 (예: "서울 강남구 역삼동")

    Returns:
        구조화된 지역 정보:
        {
            'sido': '서울',
            'gugun': '강남구',
            'dong': '역삼동',
            'full': '서울 강남구 역삼동'
        }
    """
    result = {
        "sido": None,
        "gugun": None,
        "dong": None,
        "full": raw_text.strip() if raw_text else ""
    }

    if not raw_text:
        return result

    # 공백으로 분리
    parts = raw_text.strip().split()

    if len(parts) >= 1:
        result["sido"] = normalize_sido(parts[0])

    if len(parts) >= 2:
        # 구/군 추출 (서울의 경우 '구', 그 외는 '시/군')
        gugun = parts[1].strip()
        result["gugun"] = gugun

    if len(parts) >= 3:
        # 동 추출
        result["dong"] = parts[2].strip()

    return result


def is_seoul_gu(text: str) -> bool:
    """서울시 구인지 확인"""
    return any(gu in text for gu in SEOUL_GU_LIST)


def is_gyeonggi_city(text: str) -> bool:
    """경기도 시/군인지 확인"""
    return any(city in text for city in GYEONGGI_CITY_LIST)
