"""급여 파싱 모듈"""

import re
from typing import Optional


def parse_salary(salary_text: Optional[str]) -> dict:
    """
    급여 텍스트를 파싱하여 구조화된 데이터로 변환

    Args:
        salary_text: 원본 급여 텍스트

    Returns:
        구조화된 급여 정보:
        {
            'text': '3,500~4,500만원',
            'min': 3500,  # 만원 단위
            'max': 4500,  # 만원 단위
            'type': 'annual'  # annual | monthly | hourly | negotiable
        }

    Examples:
        - "3,500~4,500만원" -> min: 3500, max: 4500, type: annual
        - "월 300만원" -> min: 3600, max: 3600, type: annual (연봉 환산)
        - "시급 12,000원" -> min: None, max: None, type: hourly
        - "회사내규에 따름" -> min: None, max: None, type: negotiable
    """
    result = {
        "text": salary_text.strip() if salary_text else "",
        "min": None,
        "max": None,
        "type": None,
    }

    if not salary_text:
        result["type"] = "negotiable"
        return result

    text = salary_text.strip()

    # 협의/내규 패턴
    if any(kw in text for kw in ["협의", "내규", "면접", "추후"]):
        result["type"] = "negotiable"
        return result

    # 숫자 추출 (쉼표 포함)
    numbers = re.findall(r"[\d,]+", text)
    numbers = [int(n.replace(",", "")) for n in numbers if n.replace(",", "").isdigit()]

    if not numbers:
        result["type"] = "negotiable"
        return result

    # 월급 패턴 확인 (연봉으로 환산)
    is_monthly = any(kw in text for kw in ["월", "월급", "월봉"])
    is_hourly = any(kw in text for kw in ["시급", "시간당", "시간"])

    if is_hourly:
        result["type"] = "hourly"
        # 시급은 연봉 환산하지 않음
        return result

    if is_monthly:
        # 월급 -> 연봉 환산 (x12)
        numbers = [n * 12 for n in numbers]
        result["type"] = "annual"
    else:
        result["type"] = "annual"

    # 숫자가 1000 이하면 만원 단위가 아닌 것으로 간주 (예: 4000만원)
    # 숫자가 1000 초과면 이미 만원 단위로 표기된 것
    normalized_numbers = []
    for n in numbers:
        if n > 100000:
            # 원 단위 (예: 40000000) -> 만원 단위로 변환
            normalized_numbers.append(n // 10000)
        elif n > 1000:
            # 이미 만원 단위로 표기 (예: 4000)
            normalized_numbers.append(n)
        else:
            # 천만원 단위로 표기 (예: 4 = 4000만원)
            normalized_numbers.append(n * 1000)

    if len(normalized_numbers) >= 2:
        result["min"] = min(normalized_numbers)
        result["max"] = max(normalized_numbers)
    elif len(normalized_numbers) == 1:
        result["min"] = normalized_numbers[0]
        result["max"] = normalized_numbers[0]

    return result


def format_salary(min_val: Optional[int], max_val: Optional[int]) -> str:
    """
    급여 범위를 읽기 좋은 형태로 포맷팅

    Args:
        min_val: 최소 연봉 (만원)
        max_val: 최대 연봉 (만원)

    Returns:
        포맷팅된 급여 문자열
    """
    if min_val is None and max_val is None:
        return "협의"

    if min_val == max_val:
        return f"{min_val:,}만원"

    if min_val and max_val:
        return f"{min_val:,}~{max_val:,}만원"

    if min_val:
        return f"{min_val:,}만원 이상"

    return f"~{max_val:,}만원"
