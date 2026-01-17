"""키워드 매칭 유틸리티

직무 검색 시 키워드-공고 매칭 스코어를 계산하는 모듈.
문자열 정규화를 사전에 수행하여 중복 연산을 방지.
"""

from dataclasses import dataclass
from typing import List, Set


@dataclass(frozen=True)
class MatchWeights:
    """매칭 가중치 설정

    Attributes:
        title: 제목 매칭 가중치 (기본 3)
        job_type: 직무 타입 매칭 가중치 (기본 2)
        keywords: 키워드 필드 매칭 가중치 (기본 1)
    """
    title: int = 3
    job_type: int = 2
    keywords: int = 1


@dataclass
class NormalizedKeyword:
    """사전 정규화된 검색 키워드

    검색 키워드를 소문자 변환 및 공백 제거한 버전을 캐시하여
    반복적인 문자열 연산을 방지.
    """
    original: str
    lower: str
    no_space: str

    @classmethod
    def from_string(cls, keyword: str) -> "NormalizedKeyword":
        """문자열에서 NormalizedKeyword 생성"""
        lower = keyword.lower().strip()
        return cls(
            original=keyword,
            lower=lower,
            no_space=lower.replace(" ", "")
        )

    def is_valid(self) -> bool:
        """유효한 키워드인지 확인 (최소 2자)"""
        return len(self.lower) >= 2


@dataclass
class NormalizedJobText:
    """사전 정규화된 공고 텍스트 필드

    공고의 텍스트 필드들을 정규화하여 캐시.
    매칭 시 반복적인 문자열 연산 방지.
    """
    title: str
    title_no_space: str
    job_type: str
    job_type_no_space: str
    job_keywords: Set[str]

    @classmethod
    def from_job(cls, job: dict) -> "NormalizedJobText":
        """공고 dict에서 NormalizedJobText 생성"""
        title = job.get("title", "").lower()
        job_type = job.get("job_type_raw", "").lower()
        keywords = {k.lower() for k in job.get("job_keywords", [])}

        return cls(
            title=title,
            title_no_space=title.replace(" ", ""),
            job_type=job_type,
            job_type_no_space=job_type.replace(" ", ""),
            job_keywords=keywords
        )


def _matches_text(nk: NormalizedKeyword, text: str, text_no_space: str) -> bool:
    """키워드가 텍스트와 매칭되는지 확인"""
    return (
        nk.lower in text or
        nk.no_space in text or
        nk.no_space in text_no_space
    )


def _matches_job_keywords(nk: NormalizedKeyword, job_keywords: Set[str]) -> bool:
    """키워드가 공고 키워드 집합과 매칭되는지 확인 (정방향만)"""
    for jk in job_keywords:
        # 검색 키워드가 공고 키워드에 포함되는지만 확인 (역방향 제거)
        if nk.lower in jk or nk.no_space in jk:
            return True
    return False


def calculate_match_score(
    job: dict,
    keywords: List[str],
    weights: MatchWeights = MatchWeights()
) -> int:
    """키워드 매칭 스코어 계산

    공고와 검색 키워드 간의 매칭 스코어를 계산.

    매칭 우선순위:
    - title 매칭: weights.title점 (기본 3)
    - job_type_raw 매칭: weights.job_type점 (기본 2)
    - job_keywords 매칭: weights.keywords점 (기본 1)

    Args:
        job: 공고 정보 dict (title, job_type_raw, job_keywords 필드 사용)
        keywords: 검색 키워드 리스트
        weights: 매칭 가중치 설정

    Returns:
        매칭 스코어 (0: 매칭 없음, 키워드 없으면 1 반환)
    """
    if not keywords:
        return 1  # 키워드 없으면 모든 공고 매칭

    job_text = NormalizedJobText.from_job(job)
    title_matched = False
    job_type_matched = False
    keywords_matched = False

    for keyword in keywords:
        nk = NormalizedKeyword.from_string(keyword)
        if not nk.is_valid():
            continue

        # Title 매칭 (공백 포함/제거 버전 모두 체크)
        if not title_matched:
            if _matches_text(nk, job_text.title, job_text.title_no_space):
                title_matched = True

        # Job type 매칭
        if not job_type_matched:
            if _matches_text(nk, job_text.job_type, job_text.job_type_no_space):
                job_type_matched = True

        # Job keywords 매칭 (양방향 포함 관계)
        if not keywords_matched:
            if _matches_job_keywords(nk, job_text.job_keywords):
                keywords_matched = True

    # 가중치 합산
    score = 0
    if title_matched:
        score += weights.title
    if job_type_matched:
        score += weights.job_type
    if keywords_matched:
        score += weights.keywords

    return score


def matches_keywords(job: dict, keywords: List[str]) -> bool:
    """키워드 매칭 여부 확인

    Args:
        job: 공고 정보 dict
        keywords: 검색 키워드 리스트

    Returns:
        하나 이상의 키워드와 매칭되면 True
    """
    return calculate_match_score(job, keywords) > 0
