"""중복 제거용 키 생성 모듈

멀티 플랫폼에서 동일 공고를 식별하기 위한 중복 제거 키를 생성합니다.

중복 판별 기준:
1. 동일 회사 (정규화된 회사명)
2. 동일/유사 직무 (정규화된 제목)
3. 동일 위치 (구 단위)

Examples:
    job1 = {"company_name": "㈜삼성전자", "title": "[신입] 소프트웨어 개발자", "location_gugun": "강남구"}
    job2 = {"company_name": "삼성전자 주식회사", "title": "소프트웨어 개발자 채용", "location_gugun": "강남구"}
    # 두 공고는 동일한 dedup_key를 가짐 -> 중복
"""

import re
import hashlib
from typing import Dict, Any

from .company import CompanyNormalizer


class DedupKeyGenerator:
    """
    중복 제거용 키 생성기

    멀티 플랫폼에서 동일 공고를 식별하기 위한 키 생성
    """

    def __init__(self):
        self.company_normalizer = CompanyNormalizer()

    # 제목에서 제거할 패턴
    TITLE_NOISE_PATTERNS = [
        r'\[.*?\]',                    # [정규직], [신입/경력] 등
        r'\(.*?\)',                    # (급구), (서울) 등
        r'【.*?】',                    # 【채용】 등
        r'〈.*?〉',                    # 〈모집〉 등
        r'<.*?>',                      # <긴급> 등
        r'\d{4,}',                     # 채용번호 (4자리 이상 숫자)
        r'모집$|채용$|구인$|공고$',   # 접미사
        r'^모집|^채용|^구인',          # 접두사
        r'신입|경력|인턴',             # 경력 조건
        r'정규직|계약직|파트타임|아르바이트',  # 고용 형태
        r'급구|긴급|상시',             # 채용 긴급도
        r'\d+기|\d+차',                # 채용 회차
    ]

    def generate(self, job_data: Dict[str, Any]) -> str:
        """
        중복 제거용 키 생성

        Args:
            job_data: {
                'company_name': str,
                'title': str,
                'location_gugun': str (구 단위)
            }

        Returns:
            dedup_key: str (MD5 해시값, 32자)

        Examples:
            >>> generator = DedupKeyGenerator()
            >>> job = {"company_name": "㈜삼성전자", "title": "백엔드 개발자", "location_gugun": "강남구"}
            >>> generator.generate(job)
            'a1b2c3d4e5f6...'  # 32자 MD5 해시
        """
        company = self._normalize_company(job_data.get('company_name', ''))
        title = self._normalize_title(job_data.get('title', ''))
        location = self._normalize_location(job_data.get('location_gugun', ''))

        # 키 생성 (구분자로 연결)
        key_string = f"{company}|{title}|{location}"

        # MD5 해시 (충분히 짧고 충돌 가능성 낮음)
        return hashlib.md5(key_string.encode('utf-8')).hexdigest()

    def generate_components(self, job_data: Dict[str, Any]) -> Dict[str, str]:
        """
        디버깅/검증용: 키 구성 요소 반환

        Args:
            job_data: 공고 데이터

        Returns:
            정규화된 구성 요소 딕셔너리

        Examples:
            >>> generator = DedupKeyGenerator()
            >>> job = {"company_name": "㈜삼성전자", "title": "[신입] 백엔드 개발자 모집", "location_gugun": "서울시 강남구"}
            >>> generator.generate_components(job)
            {
                'company_normalized': '삼성전자',
                'title_normalized': '백엔드개발자',
                'location_normalized': '강남구'
            }
        """
        return {
            'company_normalized': self._normalize_company(
                job_data.get('company_name', '')
            ),
            'title_normalized': self._normalize_title(
                job_data.get('title', '')
            ),
            'location_normalized': self._normalize_location(
                job_data.get('location_gugun', '')
            ),
        }

    def _normalize_company(self, company_name: str) -> str:
        """회사명 정규화 (비교용)"""
        return self.company_normalizer.normalize_for_comparison(company_name)

    def _normalize_title(self, title: str) -> str:
        """
        제목 정규화

        - 노이즈 패턴 제거
        - 소문자 변환
        - 공백 정리
        """
        if not title:
            return ""

        result = title

        # 노이즈 패턴 제거
        for pattern in self.TITLE_NOISE_PATTERNS:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)

        # 정규화
        result = result.lower()
        result = re.sub(r'\s+', '', result)           # 공백 제거
        result = re.sub(r'[^\w가-힣]', '', result)    # 특수문자 제거 (한글, 영숫자만 유지)

        return result

    def _normalize_location(self, location: str) -> str:
        """
        위치 정규화 (구 단위)

        - "서울시 강남구" -> "강남구"
        - "서울특별시 강남구" -> "강남구"
        - "강남구" -> "강남구"
        """
        if not location:
            return ""

        # 구/군 추출
        match = re.search(r'([가-힣]+[구군])', location)
        if match:
            return match.group(1)

        return location.strip()

    def are_duplicates(
        self,
        job1: Dict[str, Any],
        job2: Dict[str, Any]
    ) -> bool:
        """
        두 공고가 중복인지 확인

        Args:
            job1: 첫 번째 공고
            job2: 두 번째 공고

        Returns:
            중복 여부 (True/False)

        Examples:
            >>> generator = DedupKeyGenerator()
            >>> job1 = {"company_name": "㈜삼성전자", "title": "백엔드 개발자", "location_gugun": "강남구"}
            >>> job2 = {"company_name": "삼성전자 주식회사", "title": "백엔드 개발자 채용", "location_gugun": "강남구"}
            >>> generator.are_duplicates(job1, job2)
            True
        """
        return self.generate(job1) == self.generate(job2)


# 편의 함수
_generator = DedupKeyGenerator()


def generate_dedup_key(job_data: Dict[str, Any]) -> str:
    """
    중복 제거용 키 생성 (편의 함수)

    Args:
        job_data: 공고 데이터

    Returns:
        dedup_key (MD5 해시)
    """
    return _generator.generate(job_data)


def get_dedup_components(job_data: Dict[str, Any]) -> Dict[str, str]:
    """
    디버깅용: 정규화된 구성 요소 반환 (편의 함수)

    Args:
        job_data: 공고 데이터

    Returns:
        정규화된 구성 요소 딕셔너리
    """
    return _generator.generate_components(job_data)


def check_duplicates(job1: Dict[str, Any], job2: Dict[str, Any]) -> bool:
    """
    두 공고가 중복인지 확인 (편의 함수)

    Args:
        job1: 첫 번째 공고
        job2: 두 번째 공고

    Returns:
        중복 여부
    """
    return _generator.are_duplicates(job1, job2)
