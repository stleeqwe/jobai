"""
Normalizers 패키지

채용공고 데이터 정규화를 위한 모듈 모음

Modules:
    - job_type: 직무명 정규화, 카테고리 매핑
    - location: 지역명 정규화
    - salary: 급여 파싱 및 정규화
    - company: 회사명 정규화 (Phase 1)
    - dedup: 중복 제거용 키 생성 (Phase 1)
"""

# 기존 모듈
from .job_type import (
    normalize_job_type,
    get_job_category,
    get_mvp_category,
    extract_job_keywords,
)
from .location import (
    normalize_location,
    normalize_sido,
    is_seoul_gu,
    is_gyeonggi_city,
)
from .salary import (
    parse_salary,
    format_salary,
    SalaryParser,
    SalaryType,
    SalarySource,
    ParsedSalary,
)

# Phase 1: 신규 모듈
from .company import (
    CompanyNormalizer,
    normalize_company,
    normalize_company_for_comparison,
)
from .dedup import (
    DedupKeyGenerator,
    generate_dedup_key,
    get_dedup_components,
    check_duplicates,
)


__all__ = [
    # job_type
    "normalize_job_type",
    "get_job_category",
    "get_mvp_category",
    "extract_job_keywords",
    # location
    "normalize_location",
    "normalize_sido",
    "is_seoul_gu",
    "is_gyeonggi_city",
    # salary
    "parse_salary",
    "format_salary",
    "SalaryParser",
    "SalaryType",
    "SalarySource",
    "ParsedSalary",
    # company (Phase 1)
    "CompanyNormalizer",
    "normalize_company",
    "normalize_company_for_comparison",
    # dedup (Phase 1)
    "DedupKeyGenerator",
    "generate_dedup_key",
    "get_dedup_components",
    "check_duplicates",
]
