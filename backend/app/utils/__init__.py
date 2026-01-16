"""Backend utility modules"""

from .filters import matches_salary, matches_company_location
from .keyword_matcher import calculate_match_score, matches_keywords, MatchWeights
from .commute import (
    CommuteResult,
    get_job_location,
    enrich_job_with_commute,
    calculate_commutes,
    filter_and_enrich,
)

__all__ = [
    # filters
    "matches_salary",
    "matches_company_location",
    # keyword_matcher
    "calculate_match_score",
    "matches_keywords",
    "MatchWeights",
    # commute
    "CommuteResult",
    "get_job_location",
    "enrich_job_with_commute",
    "calculate_commutes",
    "filter_and_enrich",
]
