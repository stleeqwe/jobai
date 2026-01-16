"""키워드 매칭 유틸리티 테스트"""

import pytest
from app.utils.keyword_matcher import (
    NormalizedKeyword,
    NormalizedJobText,
    MatchWeights,
    calculate_match_score,
    matches_keywords,
)


class TestNormalizedKeyword:
    """NormalizedKeyword 테스트"""

    def test_from_string_basic(self):
        nk = NormalizedKeyword.from_string("Frontend")
        assert nk.original == "Frontend"
        assert nk.lower == "frontend"
        assert nk.no_space == "frontend"

    def test_from_string_with_spaces(self):
        nk = NormalizedKeyword.from_string("UI UX")
        assert nk.lower == "ui ux"
        assert nk.no_space == "uiux"

    def test_from_string_with_leading_trailing_spaces(self):
        nk = NormalizedKeyword.from_string("  React  ")
        assert nk.lower == "react"
        assert nk.no_space == "react"

    def test_is_valid_short_keyword(self):
        assert not NormalizedKeyword.from_string("a").is_valid()
        assert NormalizedKeyword.from_string("ab").is_valid()
        assert NormalizedKeyword.from_string("abc").is_valid()

    def test_is_valid_empty_keyword(self):
        assert not NormalizedKeyword.from_string("").is_valid()
        assert not NormalizedKeyword.from_string("  ").is_valid()


class TestNormalizedJobText:
    """NormalizedJobText 테스트"""

    def test_from_job_basic(self):
        job = {
            "title": "프론트엔드 개발자",
            "job_type_raw": "React/TypeScript",
            "job_keywords": ["JavaScript", "React"]
        }
        jt = NormalizedJobText.from_job(job)
        assert jt.title == "프론트엔드 개발자"
        assert jt.title_no_space == "프론트엔드개발자"
        assert jt.job_type == "react/typescript"
        assert "javascript" in jt.job_keywords
        assert "react" in jt.job_keywords

    def test_from_job_missing_fields(self):
        job = {}
        jt = NormalizedJobText.from_job(job)
        assert jt.title == ""
        assert jt.job_type == ""
        assert len(jt.job_keywords) == 0

    def test_from_job_empty_keywords(self):
        job = {"title": "개발자", "job_keywords": []}
        jt = NormalizedJobText.from_job(job)
        assert len(jt.job_keywords) == 0


class TestCalculateMatchScore:
    """calculate_match_score 테스트"""

    def test_title_match_highest_score(self):
        job = {"title": "프론트엔드 개발자", "job_type_raw": "", "job_keywords": []}
        score = calculate_match_score(job, ["프론트엔드"])
        assert score == 3  # Title weight

    def test_job_type_match_medium_score(self):
        job = {"title": "개발자", "job_type_raw": "프론트엔드", "job_keywords": []}
        score = calculate_match_score(job, ["프론트엔드"])
        assert score == 2  # Job type weight

    def test_keywords_match_lowest_score(self):
        job = {"title": "개발자", "job_type_raw": "", "job_keywords": ["프론트엔드"]}
        score = calculate_match_score(job, ["프론트엔드"])
        assert score == 1  # Keywords weight

    def test_combined_score_title_and_keywords(self):
        job = {"title": "React 개발자", "job_type_raw": "", "job_keywords": ["React"]}
        score = calculate_match_score(job, ["React"])
        assert score == 3 + 1  # Title + Keywords

    def test_combined_score_all_matches(self):
        job = {"title": "프론트엔드 개발자", "job_type_raw": "프론트엔드", "job_keywords": ["프론트엔드"]}
        score = calculate_match_score(job, ["프론트엔드"])
        assert score == 3 + 2 + 1  # All matches

    def test_no_match_returns_zero(self):
        job = {"title": "백엔드 개발자", "job_type_raw": "Java", "job_keywords": ["Spring"]}
        score = calculate_match_score(job, ["프론트엔드"])
        assert score == 0

    def test_empty_keywords_returns_one(self):
        job = {"title": "개발자", "job_type_raw": "", "job_keywords": []}
        score = calculate_match_score(job, [])
        assert score == 1

    def test_short_keyword_ignored(self):
        job = {"title": "A급 개발자", "job_type_raw": "", "job_keywords": []}
        score = calculate_match_score(job, ["A"])
        assert score == 0  # Single char keyword ignored

    def test_space_insensitive_match(self):
        job = {"title": "UI UX 디자이너", "job_type_raw": "", "job_keywords": []}
        score = calculate_match_score(job, ["UIUX"])
        assert score == 3  # Should match even without spaces

    def test_custom_weights(self):
        job = {"title": "마케팅", "job_type_raw": "", "job_keywords": []}
        weights = MatchWeights(title=10, job_type=5, keywords=2)
        score = calculate_match_score(job, ["마케팅"], weights)
        assert score == 10

    def test_bidirectional_keyword_match(self):
        # job_keywords contains "JavaScript", searching for "java" should match
        job = {"title": "개발자", "job_type_raw": "", "job_keywords": ["JavaScript"]}
        score = calculate_match_score(job, ["java"])
        assert score == 1  # "java" is contained in "javascript"


class TestMatchesKeywords:
    """matches_keywords 테스트"""

    def test_matches_returns_true(self):
        job = {"title": "프론트엔드 개발자", "job_type_raw": "", "job_keywords": []}
        assert matches_keywords(job, ["프론트엔드"]) is True

    def test_no_match_returns_false(self):
        job = {"title": "백엔드 개발자", "job_type_raw": "", "job_keywords": []}
        assert matches_keywords(job, ["프론트엔드"]) is False

    def test_empty_keywords_returns_true(self):
        job = {"title": "개발자", "job_type_raw": "", "job_keywords": []}
        assert matches_keywords(job, []) is True
