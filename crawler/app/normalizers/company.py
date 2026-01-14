"""회사명 정규화 모듈

한국 회사명의 다양한 표기를 통일된 형태로 변환합니다.

Examples:
    - "㈜삼성전자" -> ("삼성전자", "stock")
    - "(주)삼성전자" -> ("삼성전자", "stock")
    - "주식회사 네이버" -> ("네이버", "stock")
    - "Samsung Electronics Co., Ltd." -> ("Samsung Electronics", None)
"""

import re
from typing import Optional, Tuple


class CompanyNormalizer:
    """
    한국 회사명 정규화 클래스

    목적: 동일 회사의 다양한 표기를 통일된 형태로 변환
    """

    # 법인 유형 패턴 (우선순위 순)
    CORP_PATTERNS = {
        # 주식회사
        'stock': [
            r'㈜',           # 특수문자
            r'\(주\)',       # 괄호 표기
            r'주식회사',     # 전체 표기
        ],
        # 유한회사
        'limited': [
            r'㈲',
            r'\(유\)',
            r'유한책임회사',
            r'유한회사',
        ],
        # 합자/합명
        'partnership': [
            r'합자회사',
            r'합명회사',
        ],
    }

    # 영문 법인 표기 (순서 중요: 긴 패턴 먼저)
    ENGLISH_CORP_PATTERNS = [
        r'\s*,?\s*Co\.,?\s*Ltd\.?$',       # Co., Ltd.
        r'\s*,?\s*Corporation$',            # Corporation
        r'\s*,?\s*Incorporated$',           # Incorporated
        r'\s*,?\s*Inc\.?$',                 # Inc.
        r'\s*,?\s*Corp\.?$',                # Corp.
        r'\s*,?\s*Ltd\.?$',                 # Ltd.
        r'\s*,?\s*LLC\.?$',                 # LLC
        r'\s*,?\s*L\.?L\.?C\.?$',           # L.L.C.
    ]

    def normalize(self, company_name: str) -> Tuple[str, Optional[str]]:
        """
        회사명 정규화

        Args:
            company_name: 원본 회사명

        Returns:
            (정규화된 회사명, 법인유형)
            법인유형: 'stock' | 'limited' | 'partnership' | None

        Examples:
            >>> normalizer = CompanyNormalizer()
            >>> normalizer.normalize("㈜삼성전자")
            ("삼성전자", "stock")
            >>> normalizer.normalize("주식회사 네이버")
            ("네이버", "stock")
            >>> normalizer.normalize("삼성전자")
            ("삼성전자", None)
        """
        if not company_name:
            return ("", None)

        name = company_name.strip()
        corp_type = None

        # 1. 법인 유형 추출 및 제거
        for ctype, patterns in self.CORP_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, name):
                    corp_type = ctype
                    name = re.sub(pattern, '', name)
                    break
            if corp_type:
                break

        # 2. 영문 법인 표기 제거
        for pattern in self.ENGLISH_CORP_PATTERNS:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)

        # 3. 노이즈 제거
        name = re.sub(r'\s+', ' ', name)      # 연속 공백 -> 단일 공백
        name = re.sub(r'[·•‧∙]', '', name)    # 가운뎃점 변형들

        # 4. 양끝 공백 및 특수문자 정리
        name = name.strip()
        name = re.sub(r'^[\s\-\_\.\,]+|[\s\-\_\.\,]+$', '', name)

        return (name, corp_type)

    def normalize_for_comparison(self, company_name: str) -> str:
        """
        비교용 정규화 (더 aggressive한 정규화)

        중복 검사 시 사용. 대소문자, 공백 등 모두 제거.

        Args:
            company_name: 원본 회사명

        Returns:
            비교용 정규화된 문자열

        Examples:
            >>> normalizer = CompanyNormalizer()
            >>> normalizer.normalize_for_comparison("㈜삼성전자")
            "삼성전자"
            >>> normalizer.normalize_for_comparison("삼성전자 주식회사")
            "삼성전자"
            >>> # 두 결과가 동일 -> 같은 회사로 판단
        """
        name, _ = self.normalize(company_name)

        # 추가 정규화
        name = name.lower()
        name = re.sub(r'[\s\-\_\.\,]', '', name)  # 공백/구두점 제거

        return name


# 편의 함수
_normalizer = CompanyNormalizer()


def normalize_company(company_name: str) -> Tuple[str, Optional[str]]:
    """
    회사명 정규화 (편의 함수)

    Args:
        company_name: 원본 회사명

    Returns:
        (정규화된 회사명, 법인유형)
    """
    return _normalizer.normalize(company_name)


def normalize_company_for_comparison(company_name: str) -> str:
    """
    비교용 회사명 정규화 (편의 함수)

    Args:
        company_name: 원본 회사명

    Returns:
        비교용 정규화된 문자열
    """
    return _normalizer.normalize_for_comparison(company_name)
