"""
서울 지하철 그래프 자료구조

Dijkstra 알고리즘을 사용한 최단경로 계산과
Haversine 공식을 사용한 최근접 역 찾기를 제공합니다.
"""

import heapq
import math
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SubwayGraph:
    """서울 지하철 그래프 자료구조"""

    def __init__(self):
        # 인접 리스트: {station_id: [(neighbor_id, minutes), ...]}
        self.adjacency: Dict[str, List[Tuple[str, int]]] = {}

        # 역 정보: {station_id: {name, line, lat, lng, is_transfer}}
        self.stations: Dict[str, Dict] = {}

        # 좌표 목록: [(lat, lng, station_id), ...] - 최근접 역 검색용
        self.station_coords: List[Tuple[float, float, str]] = []

        # 역명 → station_id 매핑 (빠른 조회용)
        self.name_to_ids: Dict[str, List[str]] = {}

        self._initialized = False

    def load_from_json(self, data_dir: str) -> bool:
        """
        JSON 파일에서 그래프 데이터 로드

        Args:
            data_dir: stations.json, edges.json, transfers.json 위치

        Returns:
            성공 여부
        """
        data_path = Path(data_dir)

        try:
            # 역 정보 로드
            stations_file = data_path / "stations.json"
            if not stations_file.exists():
                logger.error(f"stations.json 없음: {stations_file}")
                return False

            with open(stations_file, encoding="utf-8") as f:
                stations_data = json.load(f)

            for s in stations_data:
                station_id = s["id"]
                self.stations[station_id] = s
                self.adjacency[station_id] = []

                # 좌표 저장
                lat, lng = s.get("lat", 0), s.get("lng", 0)
                if lat and lng:
                    self.station_coords.append((lat, lng, station_id))

                # 역명 → ID 매핑
                name = s.get("name", "")
                if name not in self.name_to_ids:
                    self.name_to_ids[name] = []
                self.name_to_ids[name].append(station_id)

            logger.info(f"역 로드: {len(self.stations)}개")

            # 엣지 로드
            edges_file = data_path / "edges.json"
            if edges_file.exists():
                with open(edges_file, encoding="utf-8") as f:
                    edges_data = json.load(f)

                edge_count = 0
                for e in edges_data:
                    from_id = e["from"]
                    to_id = e["to"]
                    minutes = e.get("minutes", 2)

                    if from_id in self.adjacency and to_id in self.stations:
                        # 양방향 엣지
                        self.adjacency[from_id].append((to_id, minutes))
                        if to_id not in self.adjacency:
                            self.adjacency[to_id] = []
                        self.adjacency[to_id].append((from_id, minutes))
                        edge_count += 1

                logger.info(f"엣지 로드: {edge_count}개")

            # 환승 엣지 로드
            transfers_file = data_path / "transfers.json"
            if transfers_file.exists():
                with open(transfers_file, encoding="utf-8") as f:
                    transfers_data = json.load(f)

                transfer_count = 0
                for t in transfers_data:
                    from_id = t["from"]
                    to_id = t["to"]
                    minutes = t.get("minutes", 3)

                    if from_id in self.adjacency and to_id in self.stations:
                        self.adjacency[from_id].append((to_id, minutes))
                        transfer_count += 1

                logger.info(f"환승 엣지 로드: {transfer_count}개")

            self._initialized = True
            return True

        except Exception as e:
            logger.exception(f"그래프 로드 오류: {e}")
            return False

    def is_initialized(self) -> bool:
        """그래프 초기화 여부"""
        return self._initialized and len(self.stations) > 0

    def dijkstra(
        self,
        start: str,
        end: str
    ) -> Tuple[Optional[int], List[str]]:
        """
        Dijkstra 알고리즘으로 최단경로 계산

        Args:
            start: 출발역 ID
            end: 도착역 ID

        Returns:
            (총 소요시간(분), 경로 리스트) 또는 (None, [])
        """
        if start not in self.adjacency or end not in self.adjacency:
            return None, []

        if start == end:
            return 0, [start]

        distances = {start: 0}
        previous: Dict[str, Optional[str]] = {start: None}
        heap = [(0, start)]
        visited = set()

        while heap:
            current_dist, current = heapq.heappop(heap)

            if current in visited:
                continue
            visited.add(current)

            if current == end:
                # 경로 재구성
                path = []
                node: Optional[str] = end
                while node:
                    path.append(node)
                    node = previous.get(node)
                return current_dist, path[::-1]

            for neighbor, weight in self.adjacency.get(current, []):
                if neighbor in visited:
                    continue

                new_dist = current_dist + weight
                if new_dist < distances.get(neighbor, float('inf')):
                    distances[neighbor] = new_dist
                    previous[neighbor] = current
                    heapq.heappush(heap, (new_dist, neighbor))

        return None, []

    def find_nearest_station(
        self,
        lat: float,
        lng: float,
        walking_speed_mpm: float = 80.0
    ) -> Tuple[Optional[str], int]:
        """
        좌표에서 가장 가까운 역 찾기

        Args:
            lat: 위도
            lng: 경도
            walking_speed_mpm: 도보 속도 (미터/분), 기본 80m/분 = 4.8km/h

        Returns:
            (station_id, 도보 시간(분)) 또는 (None, 0)
        """
        if not self.station_coords:
            return None, 0

        min_dist = float('inf')
        nearest_id = None

        for s_lat, s_lng, station_id in self.station_coords:
            dist = self._haversine_distance(lat, lng, s_lat, s_lng)
            if dist < min_dist:
                min_dist = dist
                nearest_id = station_id

        if nearest_id is None:
            return None, 0

        # 도보 시간 계산 (미터 → 분)
        walking_minutes = int(min_dist / walking_speed_mpm) + 1
        walking_minutes = max(1, min(walking_minutes, 30))  # 1~30분 범위

        return nearest_id, walking_minutes

    def find_station_by_name(self, name: str) -> Optional[str]:
        """
        역명으로 station_id 찾기

        Args:
            name: 역명 (예: "강남역", "강남")

        Returns:
            station_id 또는 None
        """
        # "역" 접미사 처리
        normalized = name.strip()
        if not normalized.endswith("역"):
            normalized += "역"

        # 직접 매칭
        if normalized in self.name_to_ids:
            return self.name_to_ids[normalized][0]  # 첫 번째 호선 반환

        # 부분 매칭 (예: "강남" → "강남역")
        for station_name, ids in self.name_to_ids.items():
            if name in station_name or station_name in name:
                return ids[0]

        return None

    def get_station_coords(self, station_id: str) -> Optional[Tuple[float, float]]:
        """역 좌표 조회"""
        station = self.stations.get(station_id)
        if station:
            return (station.get("lat", 0), station.get("lng", 0))
        return None

    def get_all_stations_by_name(self, name: str) -> List[str]:
        """역명에 해당하는 모든 호선의 station_id 반환"""
        normalized = name.strip()
        if not normalized.endswith("역"):
            normalized += "역"

        return self.name_to_ids.get(normalized, [])

    @staticmethod
    def _haversine_distance(
        lat1: float,
        lng1: float,
        lat2: float,
        lng2: float
    ) -> float:
        """
        두 좌표 간 거리 계산 (미터)

        Haversine 공식 사용
        """
        R = 6371000  # 지구 반경 (미터)

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lng2 - lng1)

        a = (math.sin(delta_phi / 2) ** 2 +
             math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def calculate_travel_time(
        self,
        from_lat: float,
        from_lng: float,
        to_lat: float,
        to_lng: float
    ) -> Optional[int]:
        """
        두 좌표 간 총 이동시간 계산

        = 출발지 도보 + 지하철 + 도착지 도보

        Args:
            from_lat, from_lng: 출발지 좌표
            to_lat, to_lng: 도착지 좌표

        Returns:
            총 이동시간 (분) 또는 None
        """
        # 출발역 찾기
        from_station, from_walk = self.find_nearest_station(from_lat, from_lng)
        if not from_station:
            return None

        # 도착역 찾기
        to_station, to_walk = self.find_nearest_station(to_lat, to_lng)
        if not to_station:
            return None

        # 같은 역이면 도보만
        if from_station == to_station:
            direct_walk = int(self._haversine_distance(
                from_lat, from_lng, to_lat, to_lng
            ) / 80) + 1
            return min(direct_walk, from_walk + to_walk)

        # 지하철 이동시간
        subway_time, _ = self.dijkstra(from_station, to_station)
        if subway_time is None:
            return None

        # 총 시간 = 도보 + 지하철 + 도보 + 대기 버퍼(5분)
        total = from_walk + subway_time + to_walk + 5

        return total


# 싱글톤 인스턴스
subway_graph = SubwayGraph()
