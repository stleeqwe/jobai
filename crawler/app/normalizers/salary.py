"""급여 파싱 모듈

한국 채용공고의 다양한 연봉 표현을 구조화된 데이터로 변환합니다.

Examples:
    - "연봉 4,000~5,500만원" -> min: 4000, max: 5500, type: yearly
    - "월 300만원" -> min: 3600, max: 3600, type: yearly (환산)
    - "회사내규에 따름" -> type: negotiable
    - "업계 최고 수준" -> type: unknown (무의미)
"""

import re
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


class SalaryType(Enum):
    """급여 유형"""
    YEARLY = "yearly"          # 연봉
    MONTHLY = "monthly"        # 월급 (원본 유지용)
    HOURLY = "hourly"          # 시급
    NEGOTIABLE = "negotiable"  # 협의
    UNKNOWN = "unknown"        # 파악 불가


class SalarySource(Enum):
    """급여 정보 출처"""
    DIRECT = "direct"      # 구조화된 데이터에서 직접 추출
    PARSED = "parsed"      # 텍스트에서 파싱
    UNKNOWN = "unknown"    # 파악 불가


@dataclass
class ParsedSalary:
    """파싱된 연봉 정보"""
    raw_text: str
    salary_type: SalaryType
    min_amount: Optional[int] = None  # 만원 단위
    max_amount: Optional[int] = None  # 만원 단위
    source: SalarySource = SalarySource.UNKNOWN

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환 (Firestore 저장용)"""
        return {
            "salary_text": self.raw_text,
            "salary_type": self.salary_type.value,
            "salary_min": self.min_amount,
            "salary_max": self.max_amount,
            "salary_source": self.source.value,
        }


class SalaryParser:
    """
    한국 채용공고 연봉 파서

    모든 금액은 만원 단위로 정규화
    """

    # 협의 키워드 (확장)
    NEGOTIABLE_KEYWORDS = [
        "협의", "면접", "내규", "경력에 따라", "추후",
        "별도", "상의", "조율", "논의", "결정"
    ]

    # 무의미한 표현 (파싱 스킵)
    MEANINGLESS_PATTERNS = [
        r"업계.{0,5}(최고|상위|수준)",
        r"경쟁력\s*있는",
        r"동종업계",
        r"우대\s*(조건)?$",
        r"인센티브\s*별도",
        r"성과에\s*따라",
        r"능력에\s*따라",
    ]

    def parse(self, salary_text: str, source: SalarySource = SalarySource.PARSED) -> ParsedSalary:
        """
        연봉 텍스트 파싱

        Args:
            salary_text: 원본 연봉 텍스트
            source: 데이터 출처 (direct/parsed)

        Returns:
            ParsedSalary 객체

        Examples:
            >>> parser = SalaryParser()
            >>> result = parser.parse("연봉 4,000~5,500만원")
            >>> result.min_amount, result.max_amount
            (4000, 5500)
            >>> parser.parse("회사내규에 따름").salary_type
            SalaryType.NEGOTIABLE
        """
        if not salary_text:
            return ParsedSalary(
                raw_text="",
                salary_type=SalaryType.UNKNOWN,
                source=SalarySource.UNKNOWN
            )

        text = salary_text.strip()

        # 1. 협의 케이스 체크
        if self._is_negotiable(text):
            return ParsedSalary(
                raw_text=text,
                salary_type=SalaryType.NEGOTIABLE,
                source=source
            )

        # 2. 무의미한 표현 체크
        if self._is_meaningless(text):
            return ParsedSalary(
                raw_text=text,
                salary_type=SalaryType.UNKNOWN,
                source=SalarySource.UNKNOWN
            )

        # 3. 연봉 파싱 시도
        result = self._parse_yearly(text, source)
        if result:
            return result

        # 4. 월급 파싱 시도
        result = self._parse_monthly(text, source)
        if result:
            return result

        # 5. 시급 파싱 시도
        result = self._parse_hourly(text, source)
        if result:
            return result

        # 6. 숫자만 있는 경우 (단위 추정)
        result = self._parse_numbers_only(text, source)
        if result:
            return result

        return ParsedSalary(
            raw_text=text,
            salary_type=SalaryType.UNKNOWN,
            source=SalarySource.UNKNOWN
        )

    def _is_negotiable(self, text: str) -> bool:
        """협의 여부 확인"""
        return any(kw in text for kw in self.NEGOTIABLE_KEYWORDS)

    def _is_meaningless(self, text: str) -> bool:
        """무의미한 표현 확인"""
        return any(re.search(p, text) for p in self.MEANINGLESS_PATTERNS)

    def _extract_numbers(self, text: str) -> tuple:
        """
        텍스트에서 숫자 범위 추출

        Returns:
            (min_value, max_value) - 없으면 None
        """
        # 콤마 제거
        text = text.replace(',', '')

        # 범위 패턴: "4000~5500", "4000 ~ 5500", "4000-5500"
        range_match = re.search(
            r'(\d+(?:\.\d+)?)\s*[~\-～–—]\s*(\d+(?:\.\d+)?)',
            text
        )
        if range_match:
            return (
                self._parse_number(range_match.group(1)),
                self._parse_number(range_match.group(2))
            )

        # 단일 숫자 + "이상"
        min_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:만원?)?\s*이상', text)
        if min_match:
            return (self._parse_number(min_match.group(1)), None)

        # 단일 숫자 + "이하" / "까지" / "최대"
        max_match = re.search(
            r'(?:최대|이하|까지)\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:이하|까지)',
            text
        )
        if max_match:
            val = max_match.group(1) or max_match.group(2)
            return (None, self._parse_number(val))

        # 단일 숫자
        single_match = re.search(r'(\d+(?:\.\d+)?)', text)
        if single_match:
            val = self._parse_number(single_match.group(1))
            return (val, val)

        return (None, None)

    def _parse_number(self, text: str) -> Optional[int]:
        """숫자 문자열을 정수로 변환"""
        try:
            return int(float(text))
        except (ValueError, TypeError):
            return None

    def _normalize_amount(self, amount: Optional[int]) -> Optional[int]:
        """
        금액 정규화 (만원 단위)

        - 100000000 (1억) -> 10000 (만원)
        - 4000 -> 4000 (이미 만원 단위)
        - 4 -> 4000 (4천만원으로 추정)
        """
        if amount is None:
            return None

        if amount > 100000:
            # 원 단위 (예: 40000000) -> 만원 단위로 변환
            return amount // 10000
        elif amount > 1000:
            # 이미 만원 단위로 표기 (예: 4000)
            return amount
        elif amount >= 1:
            # 천만원 단위로 표기 (예: 4 = 4000만원)
            return amount * 1000

        return amount

    def _parse_yearly(self, text: str, source: SalarySource) -> Optional[ParsedSalary]:
        """연봉 패턴 파싱"""
        # 월급/시급 키워드가 있으면 연봉이 아님
        if re.search(r'월급?|월\s*\d|시급|시간당|monthly|hourly', text, re.IGNORECASE):
            return None

        # 연봉 키워드 확인
        if not re.search(r'연봉?|년|annual', text, re.IGNORECASE):
            # 키워드 없어도 "만원" 단위가 있으면 연봉으로 추정
            if not re.search(r'\d{3,4}\s*만', text):
                return None

        min_val, max_val = self._extract_numbers(text)

        if min_val is None and max_val is None:
            return None

        return ParsedSalary(
            raw_text=text,
            salary_type=SalaryType.YEARLY,
            min_amount=self._normalize_amount(min_val),
            max_amount=self._normalize_amount(max_val),
            source=source
        )

    def _parse_monthly(self, text: str, source: SalarySource) -> Optional[ParsedSalary]:
        """월급 패턴 파싱 -> 연봉으로 변환"""
        if not re.search(r'월급?|월\s*\d|monthly', text, re.IGNORECASE):
            return None

        min_val, max_val = self._extract_numbers(text)

        if min_val is None and max_val is None:
            return None

        # 월급은 일반적으로 만원 단위로 표기 (예: "월 300만원" = 300만원)
        # 300만원 * 12 = 3600만원 (연봉)
        # normalize_amount를 적용하지 않음 (이미 만원 단위로 가정)
        return ParsedSalary(
            raw_text=text,
            salary_type=SalaryType.YEARLY,  # 연봉으로 통일
            min_amount=min_val * 12 if min_val else None,
            max_amount=max_val * 12 if max_val else None,
            source=source
        )

    def _parse_hourly(self, text: str, source: SalarySource) -> Optional[ParsedSalary]:
        """시급 패턴 파싱"""
        if not re.search(r'시급|시간당|hourly', text, re.IGNORECASE):
            return None

        min_val, max_val = self._extract_numbers(text)

        if min_val is None and max_val is None:
            return None

        # 시급은 원 단위 그대로 저장 (연봉 환산 안 함)
        return ParsedSalary(
            raw_text=text,
            salary_type=SalaryType.HOURLY,
            min_amount=min_val,
            max_amount=max_val,
            source=source
        )

    def _parse_numbers_only(self, text: str, source: SalarySource) -> Optional[ParsedSalary]:
        """
        숫자만 있는 경우 단위 추정

        - 3000~6000: 연봉 (만원)
        - 200~500: 월급 (만원) -> 연봉 변환
        - 10000~20000: 시급 (원)
        """
        min_val, max_val = self._extract_numbers(text)

        if min_val is None and max_val is None:
            return None

        # 대표값으로 판단
        ref_val = min_val or max_val

        # 연봉 범위 (1000~15000만원)
        if 1000 <= ref_val <= 20000:
            return ParsedSalary(
                raw_text=text,
                salary_type=SalaryType.YEARLY,
                min_amount=min_val,
                max_amount=max_val,
                source=source
            )

        # 월급 범위 (100~1000만원)
        if 100 <= ref_val < 1000:
            return ParsedSalary(
                raw_text=text,
                salary_type=SalaryType.YEARLY,
                min_amount=min_val * 12 if min_val else None,
                max_amount=max_val * 12 if max_val else None,
                source=source
            )

        # 시급 범위 (8000~100000원)
        if 8000 <= ref_val <= 100000:
            return ParsedSalary(
                raw_text=text,
                salary_type=SalaryType.HOURLY,
                min_amount=min_val,
                max_amount=max_val,
                source=source
            )

        return None


# ========== 하위 호환성을 위한 래퍼 함수 ==========

_parser = SalaryParser()


def parse_salary(salary_text: Optional[str]) -> dict:
    """
    급여 텍스트를 파싱하여 구조화된 데이터로 변환 (하위 호환)

    Args:
        salary_text: 원본 급여 텍스트

    Returns:
        구조화된 급여 정보:
        {
            'text': '3,500~4,500만원',
            'min': 3500,  # 만원 단위
            'max': 4500,  # 만원 단위
            'type': 'yearly',  # yearly | monthly | hourly | negotiable | unknown
            'source': 'parsed'  # direct | parsed | unknown
        }

    Examples:
        - "3,500~4,500만원" -> min: 3500, max: 4500, type: yearly
        - "월 300만원" -> min: 3600, max: 3600, type: yearly (연봉 환산)
        - "시급 12,000원" -> min: 12000, max: 12000, type: hourly
        - "회사내규에 따름" -> min: None, max: None, type: negotiable
    """
    result = _parser.parse(salary_text or "")

    # 하위 호환 형식으로 변환
    # type 필드는 기존 코드와 호환을 위해 yearly -> annual 변환 안 함
    # (새 코드는 yearly 사용, 기존 코드가 annual 기대하면 별도 처리)
    type_mapping = {
        SalaryType.YEARLY: "annual",      # 기존 호환
        SalaryType.MONTHLY: "monthly",
        SalaryType.HOURLY: "hourly",
        SalaryType.NEGOTIABLE: "negotiable",
        SalaryType.UNKNOWN: "negotiable",  # 기존 동작 유지
    }

    return {
        "text": result.raw_text,
        "min": result.min_amount,
        "max": result.max_amount,
        "type": type_mapping.get(result.salary_type, "negotiable"),
        "source": result.source.value,
    }


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
