"""통근시간 유틸리티 테스트"""

import pytest
from unittest.mock import Mock
from app.utils.commute import (
    CommuteResult,
    get_job_location,
    enrich_job_with_commute,
    calculate_commutes,
    filter_and_enrich,
)


class TestCommuteResult:
    """CommuteResult 테스트"""

    def test_from_service_result_basic(self):
        raw = {
            "minutes": 30,
            "text": "약 30분",
            "origin_station": "강남역",
            "destination_station": "서울역",
            "origin_walk": 5,
            "destination_walk": 10
        }
        result = CommuteResult.from_service_result(raw)

        assert result.minutes == 30
        assert result.text == "약 30분"
        assert result.origin_station == "강남역"
        assert result.dest_station == "서울역"
        assert result.origin_walk == 5
        assert result.dest_walk == 10

    def test_from_service_result_none(self):
        assert CommuteResult.from_service_result(None) is None

    def test_from_service_result_missing_fields(self):
        raw = {"minutes": 45, "text": "45분"}
        result = CommuteResult.from_service_result(raw)

        assert result.minutes == 45
        assert result.origin_station is None
        assert result.dest_station is None
        assert result.origin_walk == 0
        assert result.dest_walk == 0

    def test_from_service_result_default_minutes(self):
        raw = {"text": "계산 불가"}
        result = CommuteResult.from_service_result(raw)
        assert result.minutes == 999  # Default value

    def test_to_detail_dict(self):
        commute = CommuteResult(
            minutes=30,
            text="30분",
            origin_station="강남역",
            dest_station="역삼역"
        )
        detail = commute.to_detail_dict()

        assert detail["origin_station"] == "강남역"
        assert detail["dest_station"] == "역삼역"
        assert detail["origin_walk"] == 0
        assert detail["dest_walk"] == 0

    def test_to_detail_dict_none_stations(self):
        commute = CommuteResult(minutes=30, text="30분")
        detail = commute.to_detail_dict()

        assert detail["origin_station"] == ""
        assert detail["dest_station"] == ""


class TestGetJobLocation:
    """get_job_location 테스트"""

    def test_returns_location_full(self):
        job = {"location_full": "서울 강남구 역삼동", "location_gugun": "강남구"}
        assert get_job_location(job) == "서울 강남구 역삼동"

    def test_fallback_to_location_gugun(self):
        job = {"location_gugun": "강남구"}
        assert get_job_location(job) == "강남구"

    def test_returns_empty_when_no_location(self):
        job = {}
        assert get_job_location(job) == ""

    def test_prefers_location_full_over_gugun(self):
        job = {"location_full": "서울 강남구", "location_gugun": "서초구"}
        assert get_job_location(job) == "서울 강남구"


class TestEnrichJobWithCommute:
    """enrich_job_with_commute 테스트"""

    def test_adds_commute_fields(self):
        job = {"id": "1", "title": "개발자"}
        commute = CommuteResult(
            minutes=30,
            text="약 30분",
            origin_station="강남역",
            dest_station="역삼역"
        )

        enriched = enrich_job_with_commute(job, commute)

        assert enriched["commute_minutes"] == 30
        assert enriched["commute_text"] == "약 30분"
        assert enriched["commute_detail"]["origin_station"] == "강남역"
        assert enriched["commute_detail"]["dest_station"] == "역삼역"

    def test_does_not_modify_original(self):
        job = {"id": "1", "title": "개발자"}
        commute = CommuteResult(minutes=30, text="30분")

        enriched = enrich_job_with_commute(job, commute)

        assert "commute_minutes" not in job
        assert "commute_minutes" in enriched

    def test_preserves_original_fields(self):
        job = {"id": "1", "title": "개발자", "salary": "5000만원"}
        commute = CommuteResult(minutes=30, text="30분")

        enriched = enrich_job_with_commute(job, commute)

        assert enriched["id"] == "1"
        assert enriched["title"] == "개발자"
        assert enriched["salary"] == "5000만원"


class TestCalculateCommutes:
    """calculate_commutes 테스트"""

    def test_calculates_commute_for_jobs(self):
        jobs = [
            {"id": "1", "location_full": "강남구"},
            {"id": "2", "location_full": "서초구"}
        ]

        mock_service = Mock()
        mock_service.calculate.side_effect = [
            {"minutes": 20, "text": "20분"},
            {"minutes": 30, "text": "30분"}
        ]

        results = calculate_commutes(jobs, "신촌", mock_service)

        assert len(results) == 2
        assert results[0][1].minutes == 20
        assert results[1][1].minutes == 30

    def test_handles_missing_location(self):
        jobs = [{"id": "1"}]  # No location
        mock_service = Mock()

        results = calculate_commutes(jobs, "신촌", mock_service)

        assert len(results) == 1
        assert results[0][1] is None  # No commute result
        mock_service.calculate.assert_not_called()

    def test_handles_calculation_failure(self):
        jobs = [{"id": "1", "location_full": "강남구"}]
        mock_service = Mock()
        mock_service.calculate.return_value = None

        results = calculate_commutes(jobs, "신촌", mock_service)

        assert len(results) == 1
        assert results[0][1] is None


class TestFilterAndEnrich:
    """filter_and_enrich 테스트"""

    def test_no_filter_includes_all_with_commute(self):
        pairs = [
            ({"id": "1"}, CommuteResult(minutes=30, text="30분")),
            ({"id": "2"}, CommuteResult(minutes=60, text="60분")),
        ]

        results = filter_and_enrich(pairs, max_minutes=None)

        assert len(results) == 2
        assert results[0]["commute_minutes"] == 30
        assert results[1]["commute_minutes"] == 60

    def test_no_filter_includes_jobs_without_commute(self):
        pairs = [
            ({"id": "1"}, CommuteResult(minutes=30, text="30분")),
            ({"id": "2"}, None),  # No commute
        ]

        results = filter_and_enrich(pairs, max_minutes=None)

        assert len(results) == 2
        assert "commute_minutes" not in results[1]

    def test_filter_excludes_over_max_minutes(self):
        pairs = [
            ({"id": "1"}, CommuteResult(minutes=30, text="30분")),
            ({"id": "2"}, CommuteResult(minutes=60, text="60분")),
        ]

        results = filter_and_enrich(pairs, max_minutes=45)

        assert len(results) == 1
        assert results[0]["id"] == "1"

    def test_filter_excludes_jobs_without_commute(self):
        pairs = [
            ({"id": "1"}, CommuteResult(minutes=30, text="30분")),
            ({"id": "2"}, None),  # No commute - should be excluded when filtering
        ]

        results = filter_and_enrich(pairs, max_minutes=45)

        assert len(results) == 1
        assert results[0]["id"] == "1"

    def test_filter_at_boundary(self):
        pairs = [
            ({"id": "1"}, CommuteResult(minutes=45, text="45분")),
        ]

        # Exactly at max_minutes should be included
        results = filter_and_enrich(pairs, max_minutes=45)
        assert len(results) == 1

        # Just over should be excluded
        results = filter_and_enrich(pairs, max_minutes=44)
        assert len(results) == 0

    def test_enriches_all_commute_fields(self):
        commute = CommuteResult(
            minutes=30,
            text="약 30분",
            origin_station="강남역",
            dest_station="역삼역",
            origin_walk=5,
            dest_walk=10
        )
        pairs = [({"id": "1"}, commute)]

        results = filter_and_enrich(pairs, max_minutes=None)

        assert results[0]["commute_minutes"] == 30
        assert results[0]["commute_text"] == "약 30분"
        assert results[0]["commute_detail"]["origin_station"] == "강남역"
        assert results[0]["commute_detail"]["dest_station"] == "역삼역"
