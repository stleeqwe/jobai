"""
서울 지하철 기반 통근시간 계산 서비스

Google Maps API 대신 공공데이터를 활용하여 비용 없이 통근시간을 계산합니다.
MapsService와 동일한 인터페이스를 제공합니다.

지원 노선: 1-9호선 + 신분당선
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.services.seoul_subway_commute import SeoulSubwayCommute

logger = logging.getLogger(__name__)


class SubwayService:
    """서울 지하철 기반 통근시간 계산 서비스"""

    def __init__(self):
        self._commute: Optional[SeoulSubwayCommute] = None
        self._initialized = False

    async def initialize(self) -> bool:
        """
        서비스 초기화 - 내장 데이터 로드

        Returns:
            성공 여부
        """
        if self._initialized:
            return True

        try:
            self._commute = SeoulSubwayCommute()
            self._initialized = self._commute.is_initialized()

            if self._initialized:
                stats = self._commute.get_stats()
                logger.info(
                    f"SubwayService 초기화 완료: "
                    f"{stats['stations']}개 역, {stats['edges']}개 구간"
                )
            else:
                logger.error("SubwayService 초기화 실패")

        except Exception as e:
            logger.exception(f"SubwayService 초기화 오류: {e}")
            self._initialized = False

        return self._initialized

    def is_available(self) -> bool:
        """서비스 사용 가능 여부"""
        if not self._initialized:
            # 동기적으로 초기화 시도
            try:
                self._commute = SeoulSubwayCommute()
                self._initialized = self._commute.is_initialized()
            except Exception:
                self._initialized = False

        return self._initialized and self._commute is not None

    async def filter_jobs_by_travel_time(
        self,
        jobs: List[Dict[str, Any]],
        origin: str,
        max_minutes: int
    ) -> List[Dict[str, Any]]:
        """
        통근시간 기준 공고 필터링

        MapsService.filter_jobs_by_travel_time()과 동일한 인터페이스

        Args:
            jobs: 공고 리스트 (location_full 필드 필요)
            origin: 출발지 (역명, 주소, 또는 "lat,lng" 좌표)
            max_minutes: 최대 통근시간 (분)

        Returns:
            통근시간 조건 충족 공고 (travel_time_minutes, travel_time_text 필드 추가)
        """
        if not self.is_available():
            logger.warning("SubwayService 사용 불가 - 초기화 필요")
            return []

        if not jobs:
            return []

        logger.info(f"출발지: {origin}, 최대 {max_minutes}분")

        # SeoulSubwayCommute.filter_jobs() 호출
        results = self._commute.filter_jobs(
            jobs=jobs,
            origin=origin,
            max_minutes=max_minutes
        )

        logger.info(f"통근시간 필터: {len(jobs)}건 → {len(results)}건 (최대 {max_minutes}분)")

        return results

    def get_stats(self) -> Dict[str, int]:
        """통계 정보"""
        if self._commute:
            return self._commute.get_stats()
        return {'stations': 0, 'edges': 0, 'lines': 0}


# 싱글톤 인스턴스
subway_service = SubwayService()


async def initialize_subway_service() -> bool:
    """서비스 초기화 (main.py에서 호출)"""
    return await subway_service.initialize()


def check_subway_service() -> bool:
    """서비스 상태 확인"""
    return subway_service.is_available()
