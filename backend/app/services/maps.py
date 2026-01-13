"""Google Maps API 서비스 모듈 - 이동시간 계산"""

import logging
from typing import List, Optional, Dict, Any
import googlemaps

from app.config import settings

logger = logging.getLogger(__name__)

# Distance Matrix API 배치 크기 제한
BATCH_SIZE = 25


class MapsService:
    """Google Maps Distance Matrix API 서비스"""

    def __init__(self):
        self.client = None
        if settings.GOOGLE_MAPS_API_KEY:
            self.client = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)

    def is_available(self) -> bool:
        """Maps API 사용 가능 여부"""
        return self.client is not None

    async def calculate_travel_times(
        self,
        origin: str,
        destinations: List[str],
        mode: str = "transit"
    ) -> List[Optional[Dict[str, Any]]]:
        """
        여러 목적지까지 이동시간 일괄 계산

        Args:
            origin: 출발지 (예: "을지로역", "강남역")
            destinations: 목적지 주소 리스트
            mode: 이동 수단 (transit=대중교통, driving=자동차)

        Returns:
            각 목적지별 이동시간 정보 리스트
            [
                {"minutes": 15, "text": "15분", "status": "OK"},
                {"minutes": None, "text": None, "status": "NOT_FOUND"},
                ...
            ]
        """
        if not self.client:
            logger.warning("Maps API 키가 설정되지 않음")
            return [None] * len(destinations)

        if not destinations:
            return []

        results = []

        # 배치 처리 (25개씩)
        for i in range(0, len(destinations), BATCH_SIZE):
            batch = destinations[i:i + BATCH_SIZE]
            batch_results = await self._process_batch(origin, batch, mode)
            results.extend(batch_results)

        return results

    def _is_coordinates(self, location: str) -> bool:
        """위치 문자열이 좌표인지 확인 (lat,lng 형식)"""
        try:
            parts = location.split(",")
            if len(parts) == 2:
                float(parts[0].strip())
                float(parts[1].strip())
                return True
        except ValueError:
            pass
        return False

    async def reverse_geocode(self, lat: float, lng: float) -> Optional[str]:
        """
        좌표를 주소로 변환 (역지오코딩)

        Args:
            lat: 위도
            lng: 경도

        Returns:
            주소 문자열 (구/동 또는 도로명 수준)
        """
        if not self.client:
            return None

        try:
            # 상세 주소를 위해 result_type 제거하고 전체 결과 가져옴
            results = self.client.reverse_geocode(
                (lat, lng),
                language="ko"
            )

            if not results:
                return None

            # 주소 컴포넌트에서 구/동 정보 추출
            address_components = results[0].get("address_components", [])

            city = ""       # 시/도
            district = ""   # 구
            neighborhood = ""  # 동
            street = ""     # 도로명

            for comp in address_components:
                types = comp.get("types", [])
                name = comp.get("long_name", "")

                if "administrative_area_level_1" in types:
                    # 서울특별시 -> 서울
                    city = name.replace("특별시", "").replace("광역시", "").replace("도", "")
                elif "sublocality_level_1" in types:
                    district = name  # 광진구
                elif "sublocality_level_2" in types:
                    neighborhood = name  # 화양동
                elif "route" in types:
                    street = name  # 아차산로

            # 주소 조합 (동 우선, 없으면 도로명)
            if city and district:
                if neighborhood:
                    return f"{city} {district} {neighborhood}"
                elif street:
                    return f"{city} {district} {street}"
                else:
                    return f"{city} {district}"

            # 폴백: formatted_address 사용
            address = results[0].get("formatted_address", "")
            parts = address.split()
            if len(parts) >= 3:
                # "대한민국 서울특별시 광진구 화양동" -> "서울특별시 광진구 화양동"
                return " ".join(parts[1:4]) if len(parts) >= 4 else " ".join(parts[1:3])
            return address

        except Exception as e:
            logger.error(f"역지오코딩 오류: {e}")

        return None

    async def _process_batch(
        self,
        origin: str,
        destinations: List[str],
        mode: str
    ) -> List[Optional[Dict[str, Any]]]:
        """배치 단위 처리"""
        try:
            # 좌표인지 확인
            if self._is_coordinates(origin):
                # 좌표면 그대로 사용
                origin_query = origin
            else:
                # 주소면 "서울, 대한민국" 추가 (정확도 향상)
                origin_query = f"{origin}, 서울, 대한민국"

            response = self.client.distance_matrix(
                origins=[origin_query],
                destinations=destinations,
                mode=mode,
                language="ko",
                region="kr"
            )

            results = []
            elements = response.get("rows", [{}])[0].get("elements", [])

            for element in elements:
                status = element.get("status", "UNKNOWN")

                if status == "OK":
                    duration = element.get("duration", {})
                    minutes = duration.get("value", 0) // 60
                    text = duration.get("text", "")

                    results.append({
                        "minutes": minutes,
                        "text": text,
                        "status": "OK"
                    })
                else:
                    results.append({
                        "minutes": None,
                        "text": None,
                        "status": status
                    })

            return results

        except Exception as e:
            logger.error(f"Maps API 호출 오류: {e}")
            return [None] * len(destinations)

    async def filter_jobs_by_travel_time(
        self,
        jobs: List[Dict[str, Any]],
        origin: str,
        max_minutes: int
    ) -> List[Dict[str, Any]]:
        """
        이동시간 기준으로 공고 필터링

        Args:
            jobs: 공고 리스트 (location_full 필드 필요)
            origin: 출발지
            max_minutes: 최대 이동시간 (분)

        Returns:
            이동시간 조건 충족 공고 (이동시간순 정렬)
        """
        # 주소 있는 공고만 필터링
        jobs_with_address = []
        jobs_without_address = []

        for job in jobs:
            location = job.get("location_full") or job.get("location")
            if location and location.strip():
                jobs_with_address.append(job)
            else:
                jobs_without_address.append(job)

        if not jobs_with_address:
            logger.info("주소가 있는 공고가 없음")
            return []

        # 목적지 주소 추출
        destinations = []
        for job in jobs_with_address:
            location = job.get("location_full") or job.get("location", "")
            # 주소에 "대한민국" 추가하여 정확도 향상
            if "대한민국" not in location and "한국" not in location:
                location = f"{location}, 대한민국"
            destinations.append(location)

        # 이동시간 계산
        travel_times = await self.calculate_travel_times(origin, destinations)

        # 조건 충족 공고 필터링
        results = []
        for job, travel_info in zip(jobs_with_address, travel_times):
            if travel_info and travel_info.get("status") == "OK":
                minutes = travel_info.get("minutes")
                if minutes is not None and minutes <= max_minutes:
                    job_copy = dict(job)
                    job_copy["travel_time_minutes"] = minutes
                    job_copy["travel_time_text"] = travel_info.get("text", f"{minutes}분")
                    results.append(job_copy)

        # 이동시간순 정렬
        results.sort(key=lambda x: x.get("travel_time_minutes", 999))

        logger.info(
            f"거리 필터링: {len(jobs_with_address)}건 중 "
            f"{len(results)}건 통과 (최대 {max_minutes}분)"
        )

        return results


# 싱글톤 인스턴스
maps_service = MapsService()


def check_maps_api() -> bool:
    """Maps API 연결 상태 확인"""
    return maps_service.is_available()
