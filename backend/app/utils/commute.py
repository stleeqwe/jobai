"""통근시간 계산 유틸리티

지하철 기반 통근시간 계산 및 공고 데이터 보강을 위한 유틸리티.
계산 로직과 필터링 로직을 분리하여 테스트 용이성 확보.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple, Any


@dataclass
class CommuteResult:
    """통근시간 계산 결과

    Attributes:
        minutes: 총 통근시간 (분)
        text: 포맷팅된 통근시간 텍스트 (예: "약 30분")
        origin_station: 출발 역명
        dest_station: 도착 역명
        origin_walk: 출발지→역 도보시간 (분)
        dest_walk: 역→도착지 도보시간 (분)
    """
    minutes: int
    text: str
    origin_station: Optional[str] = None
    dest_station: Optional[str] = None
    origin_walk: int = 0
    dest_walk: int = 0

    @classmethod
    def from_service_result(cls, result: Optional[dict]) -> Optional["CommuteResult"]:
        """지하철 서비스 결과 dict에서 CommuteResult 생성

        Args:
            result: subway_service.calculate() 반환값

        Returns:
            CommuteResult 또는 None (result가 None인 경우)
        """
        if result is None:
            return None

        return cls(
            minutes=result.get("minutes", 999),
            text=result.get("text", ""),
            origin_station=result.get("origin_station"),
            dest_station=result.get("destination_station"),
            origin_walk=result.get("origin_walk", 0),
            dest_walk=result.get("destination_walk", 0)
        )

    def to_detail_dict(self) -> dict:
        """commute_detail 형식의 dict 반환"""
        return {
            "origin_station": self.origin_station or "",
            "dest_station": self.dest_station or "",
            "origin_walk": self.origin_walk,
            "dest_walk": self.dest_walk
        }


def get_job_location(job: dict) -> str:
    """공고에서 위치 정보 추출

    location_full을 우선 사용, 없으면 location_gugun 사용.

    Args:
        job: 공고 정보 dict

    Returns:
        위치 문자열 (없으면 빈 문자열)
    """
    return job.get("location_full") or job.get("location_gugun", "")


def enrich_job_with_commute(job: dict, commute: CommuteResult) -> dict:
    """공고에 통근 정보를 추가한 새 dict 반환

    원본 dict를 변경하지 않고 새 dict를 생성하여 반환.

    Args:
        job: 원본 공고 dict
        commute: 계산된 통근 정보

    Returns:
        통근 정보가 추가된 새 dict
    """
    enriched = dict(job)
    enriched["commute_minutes"] = commute.minutes
    enriched["commute_text"] = commute.text
    enriched["commute_detail"] = commute.to_detail_dict()
    return enriched


def calculate_commutes(
    jobs: List[dict],
    origin: str,
    subway_service: Any
) -> List[Tuple[dict, Optional[CommuteResult]]]:
    """공고 목록에 대한 통근시간 계산

    순수 계산 함수로, 필터링은 수행하지 않음.

    Args:
        jobs: 공고 목록
        origin: 출발지 (주소 또는 역명)
        subway_service: 지하철 통근시간 계산 서비스

    Returns:
        (공고, CommuteResult) 튜플 목록
        위치 정보가 없거나 계산 실패 시 CommuteResult는 None
    """
    results: List[Tuple[dict, Optional[CommuteResult]]] = []

    for job in jobs:
        location = get_job_location(job)

        if not location:
            results.append((job, None))
            continue

        raw_result = subway_service.calculate(origin, location)
        commute = CommuteResult.from_service_result(raw_result)
        results.append((job, commute))

    return results


def filter_and_enrich(
    pairs: List[Tuple[dict, Optional[CommuteResult]]],
    max_minutes: Optional[int] = None
) -> List[dict]:
    """통근시간 필터링 및 공고 데이터 보강

    Args:
        pairs: (공고, CommuteResult) 튜플 목록
        max_minutes: 최대 통근시간 필터 (분)
            - None: 필터 없음 (통근 계산 불가 공고도 포함)
            - 숫자: 해당 시간 이하만 포함 (통근 계산 불가 공고 제외)

    Returns:
        필터링 및 통근 정보 보강된 공고 목록
    """
    results: List[dict] = []

    for job, commute in pairs:
        if commute is None:
            # 통근 정보 계산 불가
            if max_minutes is None:
                # 필터 없으면 통근 정보 없이 포함
                results.append(dict(job))
            # 필터 있으면 제외
            continue

        # 필터 적용
        if max_minutes is not None and commute.minutes > max_minutes:
            continue

        # 통근 정보 추가하여 결과에 포함
        results.append(enrich_job_with_commute(job, commute))

    return results
