"""
서울 지하철 기반 통근시간 계산 모듈

Google Maps API 없이 공공데이터 기반으로 통근시간을 계산합니다.
독립적으로 사용 가능한 단일 파일 모듈입니다.

사용법:
    from seoul_subway_commute import SeoulSubwayCommute

    commute = SeoulSubwayCommute()

    # 역명으로 계산
    result = commute.calculate("강남역", "건대입구역")
    print(result)  # {'minutes': 20, 'text': '약 20분', 'path': [...]}

    # 좌표로 계산
    result = commute.calculate_by_coords(37.497, 127.027, 37.540, 127.069)
    print(result)  # {'minutes': 31, 'text': '약 30분'}

    # 공고 필터링
    jobs = [{'id': 1, 'lat': 37.500, 'lng': 127.036}, ...]
    filtered = commute.filter_jobs(jobs, origin="강남역", max_minutes=60)
"""

import heapq
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


class SeoulSubwayCommute:
    """서울 지하철 기반 통근시간 계산기"""

    # 도보 속도 (미터/분) - 약 4.8km/h
    WALKING_SPEED_MPM = 80.0

    # 대기 시간 버퍼 (분)
    WAITING_BUFFER = 5

    # 최대 도보 시간 (분)
    MAX_WALKING_MINUTES = 30

    # 공간 인덱스 그리드 크기 (약 1km x 1km)
    GRID_SIZE = 0.01  # 위도/경도 기준

    def __init__(self, data_dir: Optional[str] = None):
        """
        초기화

        Args:
            data_dir: JSON 데이터 디렉토리 경로. None이면 내장 데이터 사용
        """
        # 인접 리스트: {station_id: [(neighbor_id, minutes), ...]}
        self.adjacency: Dict[str, List[Tuple[str, int]]] = {}

        # 역 정보: {station_id: {name, line, lat, lng, is_transfer}}
        self.stations: Dict[str, Dict] = {}

        # 좌표 목록: [(lat, lng, station_id), ...]
        self.station_coords: List[Tuple[float, float, str]] = []

        # 공간 인덱스: {(grid_x, grid_y): [(lat, lng, station_id), ...]}
        self.spatial_index: Dict[Tuple[int, int], List[Tuple[float, float, str]]] = {}

        # 역명 → station_id 매핑
        self.name_to_ids: Dict[str, List[str]] = {}

        # 구 → 대표역 매핑
        self.district_stations: Dict[str, str] = {}

        self._initialized = False

        # 데이터 로드
        if data_dir:
            self._load_from_json(data_dir)
        else:
            self._load_builtin_data()

    def _load_from_json(self, data_dir: str) -> bool:
        """JSON 파일에서 데이터 로드"""
        data_path = Path(data_dir)

        try:
            # 역 정보
            with open(data_path / "stations.json", encoding="utf-8") as f:
                stations_data = json.load(f)

            for s in stations_data:
                self._add_station(s)

            # 엣지
            edges_file = data_path / "edges.json"
            if edges_file.exists():
                with open(edges_file, encoding="utf-8") as f:
                    for e in json.load(f):
                        self._add_edge(e["from"], e["to"], e.get("minutes", 2))

            # 환승
            transfers_file = data_path / "transfers.json"
            if transfers_file.exists():
                with open(transfers_file, encoding="utf-8") as f:
                    for t in json.load(f):
                        self._add_transfer(t["from"], t["to"], t.get("minutes", 3))

            self._initialized = True
            return True

        except Exception as e:
            print(f"데이터 로드 오류: {e}")
            return False

    def _load_builtin_data(self) -> None:
        """내장 데이터 로드 (1-8호선 주요역)"""
        # 역 데이터
        stations = self._get_builtin_stations()
        for s in stations:
            self._add_station(s)

        # 엣지 데이터
        edges = self._get_builtin_edges()
        for e in edges:
            self._add_edge(e["from"], e["to"], e.get("minutes", 2))

        # 환승 데이터
        transfers = self._get_builtin_transfers()
        for t in transfers:
            self._add_transfer(t["from"], t["to"], t.get("minutes", 3))

        # 구→대표역 매핑
        self._init_district_stations()

        self._initialized = True

    def _get_grid_key(self, lat: float, lng: float) -> Tuple[int, int]:
        """좌표를 그리드 키로 변환"""
        return (int(lat / self.GRID_SIZE), int(lng / self.GRID_SIZE))

    def _add_station(self, station: Dict) -> None:
        """역 추가"""
        station_id = station["id"]
        self.stations[station_id] = station
        self.adjacency[station_id] = []

        lat, lng = station.get("lat", 0), station.get("lng", 0)
        if lat and lng:
            self.station_coords.append((lat, lng, station_id))

            # 공간 인덱스에 추가
            grid_key = self._get_grid_key(lat, lng)
            if grid_key not in self.spatial_index:
                self.spatial_index[grid_key] = []
            self.spatial_index[grid_key].append((lat, lng, station_id))

        name = station.get("name", "")
        if name not in self.name_to_ids:
            self.name_to_ids[name] = []
        self.name_to_ids[name].append(station_id)

    def _add_edge(self, from_id: str, to_id: str, minutes: int) -> None:
        """양방향 엣지 추가"""
        if from_id in self.adjacency:
            self.adjacency[from_id].append((to_id, minutes))
        if to_id not in self.adjacency:
            self.adjacency[to_id] = []
        self.adjacency[to_id].append((from_id, minutes))

    def _add_transfer(self, from_id: str, to_id: str, minutes: int) -> None:
        """환승 엣지 추가 (양방향)"""
        if from_id in self.adjacency:
            self.adjacency[from_id].append((to_id, minutes))
        if to_id in self.adjacency:
            self.adjacency[to_id].append((from_id, minutes))

    def _init_district_stations(self) -> None:
        """구→대표역 매핑 초기화"""
        self.district_stations = {
            "강남구": "line2_강남역",
            "서초구": "line2_서초역",
            "송파구": "line2_잠실역",
            "강동구": "line5_강동역",
            "광진구": "line2_건대입구역",
            "성동구": "line2_왕십리역",
            "동대문구": "line1_청량리역",
            "중랑구": "line7_상봉역",
            "성북구": "line4_성신여대입구역",
            "강북구": "line4_수유역",
            "도봉구": "line4_창동역",
            "노원구": "line4_노원역",
            "은평구": "line3_연신내역",
            "서대문구": "line5_서대문역",
            "마포구": "line6_마포구청역",
            "용산구": "line6_삼각지역",
            "중구": "line4_충무로역",
            "종로구": "line1_종로3가역",
            "영등포구": "line2_영등포구청역",
            "구로구": "line2_구로디지털단지역",
            "금천구": "line7_가산디지털단지역",
            "양천구": "line2_신정역",
            "강서구": "line5_발산역",
            "동작구": "line4_총신대입구역",
            "관악구": "line2_서울대입구역",
        }

    # =========================================================================
    # 핵심 계산 메서드
    # =========================================================================

    def calculate(
        self,
        origin: str,
        destination: str
    ) -> Optional[Dict[str, Any]]:
        """
        역명/주소로 통근시간 계산

        Args:
            origin: 출발지 (역명, 주소, 또는 "lat,lng")
            destination: 도착지 (역명, 주소, 또는 "lat,lng")

        Returns:
            {
                'minutes': 실제 소요시간,
                'text': '약 30분',
                'origin_station': '강남역',
                'destination_station': '건대입구역',
                'path': ['line2_강남역', 'line2_역삼역', ...]
            }
        """
        origin_coords = self._parse_location(origin)
        dest_coords = self._parse_location(destination)

        if not origin_coords or not dest_coords:
            return None

        return self.calculate_by_coords(
            origin_coords[0], origin_coords[1],
            dest_coords[0], dest_coords[1]
        )

    def calculate_by_coords(
        self,
        from_lat: float,
        from_lng: float,
        to_lat: float,
        to_lng: float
    ) -> Optional[Dict[str, Any]]:
        """
        좌표로 통근시간 계산

        Args:
            from_lat, from_lng: 출발지 좌표
            to_lat, to_lng: 도착지 좌표

        Returns:
            {'minutes': 31, 'text': '약 30분', ...}
        """
        if not self._initialized:
            return None

        # 출발역 찾기
        from_station, from_walk = self._find_nearest_station(from_lat, from_lng)
        if not from_station:
            return None

        # 도착역 찾기
        to_station, to_walk = self._find_nearest_station(to_lat, to_lng)
        if not to_station:
            return None

        # 같은 역이면 도보만
        if from_station == to_station:
            direct_walk = self._calculate_walking_time(
                from_lat, from_lng, to_lat, to_lng
            )
            minutes = min(direct_walk, from_walk + to_walk)
            rounded, text = self._round_to_10_minutes(minutes)
            return {
                'minutes': minutes,
                'text': text,
                'origin_station': self.stations[from_station].get('name'),
                'destination_station': self.stations[to_station].get('name'),
                'path': [from_station]
            }

        # Dijkstra로 최단경로
        subway_time, path = self._dijkstra(from_station, to_station)
        if subway_time is None:
            return None

        # 총 시간 = 도보 + 지하철 + 도보 + 대기
        total = from_walk + subway_time + to_walk + self.WAITING_BUFFER
        rounded, text = self._round_to_10_minutes(total)

        return {
            'minutes': total,
            'text': text,
            'origin_station': self.stations[from_station].get('name'),
            'destination_station': self.stations[to_station].get('name'),
            'origin_walk': from_walk,
            'destination_walk': to_walk,
            'subway_time': subway_time,
            'path': path
        }

    def filter_jobs(
        self,
        jobs: List[Dict[str, Any]],
        origin: str,
        max_minutes: int
    ) -> List[Dict[str, Any]]:
        """
        통근시간 기준 공고 필터링

        Args:
            jobs: 공고 리스트 (lat, lng 또는 location 필드 필요)
            origin: 출발지 (역명, 주소, 또는 "lat,lng")
            max_minutes: 최대 통근시간 (분)

        Returns:
            통근시간 조건 충족 공고 (travel_time_minutes, travel_time_text 추가)
        """
        if not self._initialized or not jobs:
            return []

        origin_coords = self._parse_location(origin)
        if not origin_coords:
            return []

        origin_lat, origin_lng = origin_coords
        results = []

        for job in jobs:
            job_coords = self._get_job_coordinates(job)
            if not job_coords:
                continue

            result = self.calculate_by_coords(
                origin_lat, origin_lng,
                job_coords[0], job_coords[1]
            )

            if result and result['minutes'] <= max_minutes:
                job_copy = dict(job)
                job_copy['travel_time_minutes'] = result['minutes']
                job_copy['travel_time_text'] = result['text']
                results.append(job_copy)

        # 통근시간순 정렬
        results.sort(key=lambda x: x.get('travel_time_minutes', 999))

        return results

    # =========================================================================
    # 알고리즘
    # =========================================================================

    def _dijkstra(
        self,
        start: str,
        end: str
    ) -> Tuple[Optional[int], List[str]]:
        """Dijkstra 최단경로 알고리즘"""
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

    def _find_nearest_station(
        self,
        lat: float,
        lng: float
    ) -> Tuple[Optional[str], int]:
        """좌표에서 가장 가까운 역 찾기 (공간 인덱스 사용)"""
        if not self.spatial_index:
            return None, 0

        min_dist = float('inf')
        nearest_id = None

        # 현재 그리드 + 인접 9개 셀 검색 (3x3)
        center_key = self._get_grid_key(lat, lng)
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                grid_key = (center_key[0] + dx, center_key[1] + dy)
                if grid_key not in self.spatial_index:
                    continue

                for s_lat, s_lng, station_id in self.spatial_index[grid_key]:
                    dist = self._haversine_distance(lat, lng, s_lat, s_lng)
                    if dist < min_dist:
                        min_dist = dist
                        nearest_id = station_id

        # 인접 셀에서 못 찾으면 전체 검색 (fallback)
        if nearest_id is None and self.station_coords:
            for s_lat, s_lng, station_id in self.station_coords:
                dist = self._haversine_distance(lat, lng, s_lat, s_lng)
                if dist < min_dist:
                    min_dist = dist
                    nearest_id = station_id

        if nearest_id is None:
            return None, 0

        walking_minutes = int(min_dist / self.WALKING_SPEED_MPM) + 1
        walking_minutes = max(1, min(walking_minutes, self.MAX_WALKING_MINUTES))

        return nearest_id, walking_minutes

    @staticmethod
    def _haversine_distance(
        lat1: float, lng1: float,
        lat2: float, lng2: float
    ) -> float:
        """두 좌표 간 거리 (미터)"""
        R = 6371000  # 지구 반경

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lng2 - lng1)

        a = (math.sin(delta_phi / 2) ** 2 +
             math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def _calculate_walking_time(
        self,
        lat1: float, lng1: float,
        lat2: float, lng2: float
    ) -> int:
        """두 좌표 간 도보 시간 (분)"""
        dist = self._haversine_distance(lat1, lng1, lat2, lng2)
        return int(dist / self.WALKING_SPEED_MPM) + 1

    @staticmethod
    def _round_to_10_minutes(minutes: int) -> Tuple[int, str]:
        """10분 단위 반올림"""
        rounded = round(minutes / 10) * 10
        rounded = max(10, rounded)
        return rounded, f"약 {rounded}분"

    # =========================================================================
    # 파싱 유틸리티
    # =========================================================================

    def _parse_location(self, location: str) -> Optional[Tuple[float, float]]:
        """위치 문자열 → 좌표 변환"""
        location = location.strip()

        # 1. 좌표 형식 ("lat,lng")
        if "," in location:
            try:
                parts = location.split(",")
                lat = float(parts[0].strip())
                lng = float(parts[1].strip())
                if 33 <= lat <= 39 and 124 <= lng <= 132:
                    return (lat, lng)
            except ValueError:
                pass

        # 2. 역명으로 검색
        station_id = self._find_station_by_name(location)
        if station_id:
            station = self.stations.get(station_id)
            if station:
                return (station.get('lat', 0), station.get('lng', 0))

        # 3. 구/동 이름으로 대표역
        for district, station_id in self.district_stations.items():
            if district in location:
                station = self.stations.get(station_id)
                if station:
                    return (station.get('lat', 0), station.get('lng', 0))

        return None

    def _find_station_by_name(self, name: str) -> Optional[str]:
        """역명으로 station_id 찾기"""
        normalized = name.strip()

        # 주소 형식이면 역명 매칭 스킵 (공백 포함 + 10자 이상)
        # 예: "서울 중구 수표로 23" → 역명이 아님
        if " " in normalized and len(normalized) > 10:
            return None

        if not normalized.endswith("역"):
            normalized += "역"

        # 1. 정확한 매칭
        if normalized in self.name_to_ids:
            return self.name_to_ids[normalized][0]

        # 2. "역" 제거한 base name으로 부분 매칭 (짧은 입력만)
        # "을지로역" → "을지로" → "을지로입구역" 매칭 가능
        # 단, 입력이 8자 이하일 때만 (실제 역명 길이 수준)
        base_name = normalized.rstrip("역")
        if len(base_name) <= 8:
            for station_name, ids in self.name_to_ids.items():
                station_base = station_name.rstrip("역")
                if base_name in station_base or station_base in base_name:
                    return ids[0]

        return None

    def _get_job_coordinates(self, job: Dict) -> Optional[Tuple[float, float]]:
        """공고에서 좌표 추출"""
        if job.get("lat") and job.get("lng"):
            try:
                return (float(job["lat"]), float(job["lng"]))
            except (ValueError, TypeError):
                pass

        location = job.get("location_full") or job.get("location", "")
        if location:
            return self._parse_location(location)

        return None

    # =========================================================================
    # 정보 조회
    # =========================================================================

    def get_station_info(self, name: str) -> Optional[Dict]:
        """역 정보 조회"""
        station_id = self._find_station_by_name(name)
        if station_id:
            return self.stations.get(station_id)
        return None

    def get_all_stations(self) -> List[Dict]:
        """전체 역 목록"""
        return list(self.stations.values())

    def get_stats(self) -> Dict[str, int]:
        """통계 정보"""
        return {
            'stations': len(self.stations),
            'edges': sum(len(v) for v in self.adjacency.values()) // 2,
            'lines': len(set(s.get('line', 0) for s in self.stations.values()))
        }

    def is_initialized(self) -> bool:
        """초기화 여부"""
        return self._initialized

    # =========================================================================
    # 내장 데이터 (1-8호선 주요역)
    # =========================================================================

    def _get_builtin_stations(self) -> List[Dict]:
        """내장 역 데이터"""
        return [
            # 1호선
            {"id": "line1_소요산역", "name": "소요산역", "line": 1, "lat": 37.9474, "lng": 127.0612, "is_transfer": False},
            {"id": "line1_동두천역", "name": "동두천역", "line": 1, "lat": 37.9037, "lng": 127.0608, "is_transfer": False},
            {"id": "line1_의정부역", "name": "의정부역", "line": 1, "lat": 37.7381, "lng": 127.0458, "is_transfer": False},
            {"id": "line1_회룡역", "name": "회룡역", "line": 1, "lat": 37.7197, "lng": 127.0434, "is_transfer": False},
            {"id": "line1_도봉산역", "name": "도봉산역", "line": 1, "lat": 37.6896, "lng": 127.0445, "is_transfer": True},
            {"id": "line1_창동역", "name": "창동역", "line": 1, "lat": 37.6532, "lng": 127.0476, "is_transfer": True},
            {"id": "line1_석계역", "name": "석계역", "line": 1, "lat": 37.6146, "lng": 127.0663, "is_transfer": True},
            {"id": "line1_광운대역", "name": "광운대역", "line": 1, "lat": 37.6244, "lng": 127.0615, "is_transfer": False},
            {"id": "line1_청량리역", "name": "청량리역", "line": 1, "lat": 37.5804, "lng": 127.0469, "is_transfer": True},
            {"id": "line1_동대문역", "name": "동대문역", "line": 1, "lat": 37.5710, "lng": 127.0095, "is_transfer": True},
            {"id": "line1_종로3가역", "name": "종로3가역", "line": 1, "lat": 37.5714, "lng": 126.9916, "is_transfer": True},
            {"id": "line1_종각역", "name": "종각역", "line": 1, "lat": 37.5700, "lng": 126.9828, "is_transfer": False},
            {"id": "line1_시청역", "name": "시청역", "line": 1, "lat": 37.5657, "lng": 126.9772, "is_transfer": True},
            {"id": "line1_서울역", "name": "서울역", "line": 1, "lat": 37.5547, "lng": 126.9707, "is_transfer": True},
            {"id": "line1_남영역", "name": "남영역", "line": 1, "lat": 37.5413, "lng": 126.9713, "is_transfer": False},
            {"id": "line1_용산역", "name": "용산역", "line": 1, "lat": 37.5299, "lng": 126.9649, "is_transfer": True},
            {"id": "line1_영등포역", "name": "영등포역", "line": 1, "lat": 37.5159, "lng": 126.9074, "is_transfer": False},
            {"id": "line1_신도림역", "name": "신도림역", "line": 1, "lat": 37.5089, "lng": 126.8912, "is_transfer": True},
            {"id": "line1_구로역", "name": "구로역", "line": 1, "lat": 37.5033, "lng": 126.8824, "is_transfer": False},
            {"id": "line1_인천역", "name": "인천역", "line": 1, "lat": 37.4762, "lng": 126.6174, "is_transfer": False},

            # 2호선
            {"id": "line2_시청역", "name": "시청역", "line": 2, "lat": 37.5657, "lng": 126.9772, "is_transfer": True},
            {"id": "line2_을지로입구역", "name": "을지로입구역", "line": 2, "lat": 37.5660, "lng": 126.9824, "is_transfer": False},
            {"id": "line2_을지로3가역", "name": "을지로3가역", "line": 2, "lat": 37.5664, "lng": 126.9920, "is_transfer": True},
            {"id": "line2_을지로4가역", "name": "을지로4가역", "line": 2, "lat": 37.5670, "lng": 127.0011, "is_transfer": True},
            {"id": "line2_동대문역사문화공원역", "name": "동대문역사문화공원역", "line": 2, "lat": 37.5653, "lng": 127.0094, "is_transfer": True},
            {"id": "line2_신당역", "name": "신당역", "line": 2, "lat": 37.5659, "lng": 127.0175, "is_transfer": True},
            {"id": "line2_상왕십리역", "name": "상왕십리역", "line": 2, "lat": 37.5647, "lng": 127.0295, "is_transfer": False},
            {"id": "line2_왕십리역", "name": "왕십리역", "line": 2, "lat": 37.5614, "lng": 127.0378, "is_transfer": True},
            {"id": "line2_한양대역", "name": "한양대역", "line": 2, "lat": 37.5555, "lng": 127.0434, "is_transfer": False},
            {"id": "line2_뚝섬역", "name": "뚝섬역", "line": 2, "lat": 37.5474, "lng": 127.0473, "is_transfer": False},
            {"id": "line2_성수역", "name": "성수역", "line": 2, "lat": 37.5445, "lng": 127.0559, "is_transfer": False},
            {"id": "line2_건대입구역", "name": "건대입구역", "line": 2, "lat": 37.5403, "lng": 127.0694, "is_transfer": True},
            {"id": "line2_구의역", "name": "구의역", "line": 2, "lat": 37.5354, "lng": 127.0863, "is_transfer": False},
            {"id": "line2_강변역", "name": "강변역", "line": 2, "lat": 37.5349, "lng": 127.0947, "is_transfer": False},
            {"id": "line2_잠실나루역", "name": "잠실나루역", "line": 2, "lat": 37.5208, "lng": 127.1035, "is_transfer": False},
            {"id": "line2_잠실역", "name": "잠실역", "line": 2, "lat": 37.5132, "lng": 127.1001, "is_transfer": True},
            {"id": "line2_잠실새내역", "name": "잠실새내역", "line": 2, "lat": 37.5117, "lng": 127.0864, "is_transfer": False},
            {"id": "line2_종합운동장역", "name": "종합운동장역", "line": 2, "lat": 37.5107, "lng": 127.0732, "is_transfer": False},
            {"id": "line2_삼성역", "name": "삼성역", "line": 2, "lat": 37.5089, "lng": 127.0637, "is_transfer": False},
            {"id": "line2_선릉역", "name": "선릉역", "line": 2, "lat": 37.5046, "lng": 127.0492, "is_transfer": True},
            {"id": "line2_역삼역", "name": "역삼역", "line": 2, "lat": 37.5006, "lng": 127.0365, "is_transfer": False},
            {"id": "line2_강남역", "name": "강남역", "line": 2, "lat": 37.4979, "lng": 127.0276, "is_transfer": True},
            {"id": "line2_교대역", "name": "교대역", "line": 2, "lat": 37.4934, "lng": 127.0146, "is_transfer": True},
            {"id": "line2_서초역", "name": "서초역", "line": 2, "lat": 37.4916, "lng": 127.0076, "is_transfer": False},
            {"id": "line2_방배역", "name": "방배역", "line": 2, "lat": 37.4813, "lng": 126.9976, "is_transfer": False},
            {"id": "line2_사당역", "name": "사당역", "line": 2, "lat": 37.4766, "lng": 126.9816, "is_transfer": True},
            {"id": "line2_낙성대역", "name": "낙성대역", "line": 2, "lat": 37.4768, "lng": 126.9636, "is_transfer": False},
            {"id": "line2_서울대입구역", "name": "서울대입구역", "line": 2, "lat": 37.4812, "lng": 126.9527, "is_transfer": False},
            {"id": "line2_봉천역", "name": "봉천역", "line": 2, "lat": 37.4824, "lng": 126.9418, "is_transfer": False},
            {"id": "line2_신림역", "name": "신림역", "line": 2, "lat": 37.4842, "lng": 126.9294, "is_transfer": False},
            {"id": "line2_신대방역", "name": "신대방역", "line": 2, "lat": 37.4875, "lng": 126.9130, "is_transfer": False},
            {"id": "line2_구로디지털단지역", "name": "구로디지털단지역", "line": 2, "lat": 37.4851, "lng": 126.9014, "is_transfer": False},
            {"id": "line2_대림역", "name": "대림역", "line": 2, "lat": 37.4932, "lng": 126.8958, "is_transfer": True},
            {"id": "line2_신도림역", "name": "신도림역", "line": 2, "lat": 37.5089, "lng": 126.8912, "is_transfer": True},
            {"id": "line2_문래역", "name": "문래역", "line": 2, "lat": 37.5178, "lng": 126.8986, "is_transfer": False},
            {"id": "line2_영등포구청역", "name": "영등포구청역", "line": 2, "lat": 37.5245, "lng": 126.8964, "is_transfer": True},
            {"id": "line2_당산역", "name": "당산역", "line": 2, "lat": 37.5348, "lng": 126.9023, "is_transfer": True},
            {"id": "line2_합정역", "name": "합정역", "line": 2, "lat": 37.5495, "lng": 126.9139, "is_transfer": True},
            {"id": "line2_홍대입구역", "name": "홍대입구역", "line": 2, "lat": 37.5573, "lng": 126.9236, "is_transfer": True},
            {"id": "line2_신촌역", "name": "신촌역", "line": 2, "lat": 37.5553, "lng": 126.9367, "is_transfer": False},
            {"id": "line2_이대역", "name": "이대역", "line": 2, "lat": 37.5569, "lng": 126.9459, "is_transfer": False},
            {"id": "line2_아현역", "name": "아현역", "line": 2, "lat": 37.5576, "lng": 126.9560, "is_transfer": False},
            {"id": "line2_충정로역", "name": "충정로역", "line": 2, "lat": 37.5601, "lng": 126.9635, "is_transfer": True},

            # 3호선
            {"id": "line3_대화역", "name": "대화역", "line": 3, "lat": 37.6765, "lng": 126.7492, "is_transfer": False},
            {"id": "line3_연신내역", "name": "연신내역", "line": 3, "lat": 37.6189, "lng": 126.9212, "is_transfer": True},
            {"id": "line3_불광역", "name": "불광역", "line": 3, "lat": 37.6101, "lng": 126.9298, "is_transfer": True},
            {"id": "line3_녹번역", "name": "녹번역", "line": 3, "lat": 37.6010, "lng": 126.9358, "is_transfer": False},
            {"id": "line3_홍제역", "name": "홍제역", "line": 3, "lat": 37.5891, "lng": 126.9434, "is_transfer": False},
            {"id": "line3_무악재역", "name": "무악재역", "line": 3, "lat": 37.5823, "lng": 126.9501, "is_transfer": False},
            {"id": "line3_독립문역", "name": "독립문역", "line": 3, "lat": 37.5755, "lng": 126.9590, "is_transfer": False},
            {"id": "line3_경복궁역", "name": "경복궁역", "line": 3, "lat": 37.5759, "lng": 126.9736, "is_transfer": False},
            {"id": "line3_안국역", "name": "안국역", "line": 3, "lat": 37.5764, "lng": 126.9850, "is_transfer": False},
            {"id": "line3_종로3가역", "name": "종로3가역", "line": 3, "lat": 37.5714, "lng": 126.9916, "is_transfer": True},
            {"id": "line3_을지로3가역", "name": "을지로3가역", "line": 3, "lat": 37.5664, "lng": 126.9920, "is_transfer": True},
            {"id": "line3_충무로역", "name": "충무로역", "line": 3, "lat": 37.5614, "lng": 126.9945, "is_transfer": True},
            {"id": "line3_동대입구역", "name": "동대입구역", "line": 3, "lat": 37.5576, "lng": 127.0002, "is_transfer": False},
            {"id": "line3_약수역", "name": "약수역", "line": 3, "lat": 37.5545, "lng": 127.0103, "is_transfer": True},
            {"id": "line3_금호역", "name": "금호역", "line": 3, "lat": 37.5472, "lng": 127.0186, "is_transfer": False},
            {"id": "line3_옥수역", "name": "옥수역", "line": 3, "lat": 37.5406, "lng": 127.0175, "is_transfer": True},
            {"id": "line3_압구정역", "name": "압구정역", "line": 3, "lat": 37.5271, "lng": 127.0282, "is_transfer": False},
            {"id": "line3_신사역", "name": "신사역", "line": 3, "lat": 37.5168, "lng": 127.0201, "is_transfer": False},
            {"id": "line3_잠원역", "name": "잠원역", "line": 3, "lat": 37.5115, "lng": 127.0105, "is_transfer": False},
            {"id": "line3_고속터미널역", "name": "고속터미널역", "line": 3, "lat": 37.5049, "lng": 127.0051, "is_transfer": True},
            {"id": "line3_교대역", "name": "교대역", "line": 3, "lat": 37.4934, "lng": 127.0146, "is_transfer": True},
            {"id": "line3_남부터미널역", "name": "남부터미널역", "line": 3, "lat": 37.4848, "lng": 127.0155, "is_transfer": False},
            {"id": "line3_양재역", "name": "양재역", "line": 3, "lat": 37.4841, "lng": 127.0344, "is_transfer": True},
            {"id": "line3_매봉역", "name": "매봉역", "line": 3, "lat": 37.4878, "lng": 127.0469, "is_transfer": False},
            {"id": "line3_도곡역", "name": "도곡역", "line": 3, "lat": 37.4915, "lng": 127.0548, "is_transfer": True},
            {"id": "line3_대치역", "name": "대치역", "line": 3, "lat": 37.4947, "lng": 127.0634, "is_transfer": False},
            {"id": "line3_학여울역", "name": "학여울역", "line": 3, "lat": 37.4968, "lng": 127.0714, "is_transfer": False},
            {"id": "line3_대청역", "name": "대청역", "line": 3, "lat": 37.4918, "lng": 127.0818, "is_transfer": False},
            {"id": "line3_일원역", "name": "일원역", "line": 3, "lat": 37.4836, "lng": 127.0877, "is_transfer": False},
            {"id": "line3_수서역", "name": "수서역", "line": 3, "lat": 37.4875, "lng": 127.1019, "is_transfer": True},
            {"id": "line3_오금역", "name": "오금역", "line": 3, "lat": 37.5031, "lng": 127.1281, "is_transfer": True},

            # 4호선
            {"id": "line4_당고개역", "name": "당고개역", "line": 4, "lat": 37.6724, "lng": 127.0790, "is_transfer": False},
            {"id": "line4_상계역", "name": "상계역", "line": 4, "lat": 37.6614, "lng": 127.0728, "is_transfer": False},
            {"id": "line4_노원역", "name": "노원역", "line": 4, "lat": 37.6554, "lng": 127.0616, "is_transfer": True},
            {"id": "line4_창동역", "name": "창동역", "line": 4, "lat": 37.6532, "lng": 127.0476, "is_transfer": True},
            {"id": "line4_쌍문역", "name": "쌍문역", "line": 4, "lat": 37.6479, "lng": 127.0347, "is_transfer": False},
            {"id": "line4_수유역", "name": "수유역", "line": 4, "lat": 37.6378, "lng": 127.0251, "is_transfer": False},
            {"id": "line4_미아역", "name": "미아역", "line": 4, "lat": 37.6264, "lng": 127.0260, "is_transfer": False},
            {"id": "line4_미아사거리역", "name": "미아사거리역", "line": 4, "lat": 37.6133, "lng": 127.0300, "is_transfer": False},
            {"id": "line4_길음역", "name": "길음역", "line": 4, "lat": 37.6031, "lng": 127.0249, "is_transfer": False},
            {"id": "line4_성신여대입구역", "name": "성신여대입구역", "line": 4, "lat": 37.5926, "lng": 127.0165, "is_transfer": True},
            {"id": "line4_한성대입구역", "name": "한성대입구역", "line": 4, "lat": 37.5885, "lng": 127.0065, "is_transfer": False},
            {"id": "line4_혜화역", "name": "혜화역", "line": 4, "lat": 37.5824, "lng": 127.0019, "is_transfer": False},
            {"id": "line4_동대문역", "name": "동대문역", "line": 4, "lat": 37.5710, "lng": 127.0095, "is_transfer": True},
            {"id": "line4_동대문역사문화공원역", "name": "동대문역사문화공원역", "line": 4, "lat": 37.5653, "lng": 127.0094, "is_transfer": True},
            {"id": "line4_충무로역", "name": "충무로역", "line": 4, "lat": 37.5614, "lng": 126.9945, "is_transfer": True},
            {"id": "line4_명동역", "name": "명동역", "line": 4, "lat": 37.5606, "lng": 126.9859, "is_transfer": False},
            {"id": "line4_회현역", "name": "회현역", "line": 4, "lat": 37.5585, "lng": 126.9782, "is_transfer": False},
            {"id": "line4_서울역", "name": "서울역", "line": 4, "lat": 37.5547, "lng": 126.9707, "is_transfer": True},
            {"id": "line4_숙대입구역", "name": "숙대입구역", "line": 4, "lat": 37.5448, "lng": 126.9719, "is_transfer": False},
            {"id": "line4_삼각지역", "name": "삼각지역", "line": 4, "lat": 37.5347, "lng": 126.9732, "is_transfer": True},
            {"id": "line4_신용산역", "name": "신용산역", "line": 4, "lat": 37.5289, "lng": 126.9688, "is_transfer": False},
            {"id": "line4_이촌역", "name": "이촌역", "line": 4, "lat": 37.5218, "lng": 126.9700, "is_transfer": True},
            {"id": "line4_동작역", "name": "동작역", "line": 4, "lat": 37.5070, "lng": 126.9784, "is_transfer": True},
            {"id": "line4_총신대입구역", "name": "총신대입구역", "line": 4, "lat": 37.4866, "lng": 126.9818, "is_transfer": True},
            {"id": "line4_사당역", "name": "사당역", "line": 4, "lat": 37.4766, "lng": 126.9816, "is_transfer": True},
            {"id": "line4_남태령역", "name": "남태령역", "line": 4, "lat": 37.4644, "lng": 126.9874, "is_transfer": False},
            {"id": "line4_선바위역", "name": "선바위역", "line": 4, "lat": 37.4525, "lng": 126.9913, "is_transfer": False},
            {"id": "line4_경마공원역", "name": "경마공원역", "line": 4, "lat": 37.4435, "lng": 126.9957, "is_transfer": False},
            {"id": "line4_대공원역", "name": "대공원역", "line": 4, "lat": 37.4299, "lng": 127.0095, "is_transfer": False},
            {"id": "line4_과천역", "name": "과천역", "line": 4, "lat": 37.4265, "lng": 126.9876, "is_transfer": False},
            {"id": "line4_정부과천청사역", "name": "정부과천청사역", "line": 4, "lat": 37.4234, "lng": 126.9901, "is_transfer": False},
            {"id": "line4_인덕원역", "name": "인덕원역", "line": 4, "lat": 37.3932, "lng": 126.9881, "is_transfer": False},
            {"id": "line4_평촌역", "name": "평촌역", "line": 4, "lat": 37.3900, "lng": 126.9654, "is_transfer": False},
            {"id": "line4_범계역", "name": "범계역", "line": 4, "lat": 37.3894, "lng": 126.9517, "is_transfer": False},
            {"id": "line4_금정역", "name": "금정역", "line": 4, "lat": 37.3716, "lng": 126.9426, "is_transfer": True},
            {"id": "line4_안산역", "name": "안산역", "line": 4, "lat": 37.3227, "lng": 126.8492, "is_transfer": False},
            {"id": "line4_오이도역", "name": "오이도역", "line": 4, "lat": 37.3478, "lng": 126.6869, "is_transfer": False},

            # 5호선
            {"id": "line5_방화역", "name": "방화역", "line": 5, "lat": 37.5752, "lng": 126.8154, "is_transfer": False},
            {"id": "line5_개화산역", "name": "개화산역", "line": 5, "lat": 37.5732, "lng": 126.8026, "is_transfer": False},
            {"id": "line5_김포공항역", "name": "김포공항역", "line": 5, "lat": 37.5625, "lng": 126.8010, "is_transfer": True},
            {"id": "line5_송정역", "name": "송정역", "line": 5, "lat": 37.5552, "lng": 126.8022, "is_transfer": False},
            {"id": "line5_마곡역", "name": "마곡역", "line": 5, "lat": 37.5603, "lng": 126.8245, "is_transfer": False},
            {"id": "line5_발산역", "name": "발산역", "line": 5, "lat": 37.5592, "lng": 126.8384, "is_transfer": False},
            {"id": "line5_우장산역", "name": "우장산역", "line": 5, "lat": 37.5481, "lng": 126.8361, "is_transfer": False},
            {"id": "line5_화곡역", "name": "화곡역", "line": 5, "lat": 37.5411, "lng": 126.8397, "is_transfer": False},
            {"id": "line5_까치산역", "name": "까치산역", "line": 5, "lat": 37.5317, "lng": 126.8474, "is_transfer": True},
            {"id": "line5_신정역", "name": "신정역", "line": 5, "lat": 37.5247, "lng": 126.8563, "is_transfer": False},
            {"id": "line5_목동역", "name": "목동역", "line": 5, "lat": 37.5263, "lng": 126.8665, "is_transfer": False},
            {"id": "line5_오목교역", "name": "오목교역", "line": 5, "lat": 37.5246, "lng": 126.8773, "is_transfer": False},
            {"id": "line5_양평역", "name": "양평역", "line": 5, "lat": 37.5260, "lng": 126.8862, "is_transfer": False},
            {"id": "line5_영등포구청역", "name": "영등포구청역", "line": 5, "lat": 37.5245, "lng": 126.8964, "is_transfer": True},
            {"id": "line5_영등포시장역", "name": "영등포시장역", "line": 5, "lat": 37.5228, "lng": 126.9052, "is_transfer": False},
            {"id": "line5_신길역", "name": "신길역", "line": 5, "lat": 37.5175, "lng": 126.9171, "is_transfer": True},
            {"id": "line5_여의도역", "name": "여의도역", "line": 5, "lat": 37.5216, "lng": 126.9242, "is_transfer": False},
            {"id": "line5_여의나루역", "name": "여의나루역", "line": 5, "lat": 37.5271, "lng": 126.9329, "is_transfer": False},
            {"id": "line5_마포역", "name": "마포역", "line": 5, "lat": 37.5392, "lng": 126.9456, "is_transfer": False},
            {"id": "line5_공덕역", "name": "공덕역", "line": 5, "lat": 37.5439, "lng": 126.9516, "is_transfer": True},
            {"id": "line5_애오개역", "name": "애오개역", "line": 5, "lat": 37.5532, "lng": 126.9566, "is_transfer": False},
            {"id": "line5_충정로역", "name": "충정로역", "line": 5, "lat": 37.5601, "lng": 126.9635, "is_transfer": True},
            {"id": "line5_서대문역", "name": "서대문역", "line": 5, "lat": 37.5651, "lng": 126.9666, "is_transfer": False},
            {"id": "line5_광화문역", "name": "광화문역", "line": 5, "lat": 37.5759, "lng": 126.9769, "is_transfer": False},
            {"id": "line5_종로3가역", "name": "종로3가역", "line": 5, "lat": 37.5714, "lng": 126.9916, "is_transfer": True},
            {"id": "line5_을지로4가역", "name": "을지로4가역", "line": 5, "lat": 37.5670, "lng": 127.0011, "is_transfer": True},
            {"id": "line5_동대문역사문화공원역", "name": "동대문역사문화공원역", "line": 5, "lat": 37.5653, "lng": 127.0094, "is_transfer": True},
            {"id": "line5_청구역", "name": "청구역", "line": 5, "lat": 37.5604, "lng": 127.0184, "is_transfer": True},
            {"id": "line5_신금호역", "name": "신금호역", "line": 5, "lat": 37.5547, "lng": 127.0251, "is_transfer": False},
            {"id": "line5_행당역", "name": "행당역", "line": 5, "lat": 37.5575, "lng": 127.0328, "is_transfer": False},
            {"id": "line5_왕십리역", "name": "왕십리역", "line": 5, "lat": 37.5614, "lng": 127.0378, "is_transfer": True},
            {"id": "line5_마장역", "name": "마장역", "line": 5, "lat": 37.5656, "lng": 127.0461, "is_transfer": False},
            {"id": "line5_답십리역", "name": "답십리역", "line": 5, "lat": 37.5674, "lng": 127.0521, "is_transfer": False},
            {"id": "line5_장한평역", "name": "장한평역", "line": 5, "lat": 37.5611, "lng": 127.0643, "is_transfer": False},
            {"id": "line5_군자역", "name": "군자역", "line": 5, "lat": 37.5574, "lng": 127.0793, "is_transfer": True},
            {"id": "line5_아차산역", "name": "아차산역", "line": 5, "lat": 37.5514, "lng": 127.0897, "is_transfer": False},
            {"id": "line5_광나루역", "name": "광나루역", "line": 5, "lat": 37.5452, "lng": 127.1036, "is_transfer": False},
            {"id": "line5_천호역", "name": "천호역", "line": 5, "lat": 37.5387, "lng": 127.1237, "is_transfer": True},
            {"id": "line5_강동역", "name": "강동역", "line": 5, "lat": 37.5352, "lng": 127.1321, "is_transfer": False},
            {"id": "line5_길동역", "name": "길동역", "line": 5, "lat": 37.5310, "lng": 127.1378, "is_transfer": False},
            {"id": "line5_굽은다리역", "name": "굽은다리역", "line": 5, "lat": 37.5233, "lng": 127.1357, "is_transfer": False},
            {"id": "line5_명일역", "name": "명일역", "line": 5, "lat": 37.5182, "lng": 127.1394, "is_transfer": False},
            {"id": "line5_고덕역", "name": "고덕역", "line": 5, "lat": 37.5550, "lng": 127.1543, "is_transfer": False},
            {"id": "line5_상일동역", "name": "상일동역", "line": 5, "lat": 37.5535, "lng": 127.1666, "is_transfer": False},
            {"id": "line5_마천역", "name": "마천역", "line": 5, "lat": 37.4962, "lng": 127.1446, "is_transfer": False},

            # 6호선
            {"id": "line6_응암역", "name": "응암역", "line": 6, "lat": 37.5986, "lng": 126.9143, "is_transfer": False},
            {"id": "line6_역촌역", "name": "역촌역", "line": 6, "lat": 37.6060, "lng": 126.9219, "is_transfer": False},
            {"id": "line6_불광역", "name": "불광역", "line": 6, "lat": 37.6101, "lng": 126.9298, "is_transfer": True},
            {"id": "line6_독바위역", "name": "독바위역", "line": 6, "lat": 37.6137, "lng": 126.9361, "is_transfer": False},
            {"id": "line6_연신내역", "name": "연신내역", "line": 6, "lat": 37.6189, "lng": 126.9212, "is_transfer": True},
            {"id": "line6_구산역", "name": "구산역", "line": 6, "lat": 37.6135, "lng": 126.9049, "is_transfer": False},
            {"id": "line6_새절역", "name": "새절역", "line": 6, "lat": 37.5919, "lng": 126.9119, "is_transfer": False},
            {"id": "line6_증산역", "name": "증산역", "line": 6, "lat": 37.5836, "lng": 126.9094, "is_transfer": False},
            {"id": "line6_디지털미디어시티역", "name": "디지털미디어시티역", "line": 6, "lat": 37.5776, "lng": 126.8997, "is_transfer": True},
            {"id": "line6_월드컵경기장역", "name": "월드컵경기장역", "line": 6, "lat": 37.5681, "lng": 126.8974, "is_transfer": False},
            {"id": "line6_마포구청역", "name": "마포구청역", "line": 6, "lat": 37.5631, "lng": 126.9025, "is_transfer": False},
            {"id": "line6_망원역", "name": "망원역", "line": 6, "lat": 37.5556, "lng": 126.9103, "is_transfer": False},
            {"id": "line6_합정역", "name": "합정역", "line": 6, "lat": 37.5495, "lng": 126.9139, "is_transfer": True},
            {"id": "line6_상수역", "name": "상수역", "line": 6, "lat": 37.5477, "lng": 126.9230, "is_transfer": False},
            {"id": "line6_광흥창역", "name": "광흥창역", "line": 6, "lat": 37.5475, "lng": 126.9316, "is_transfer": False},
            {"id": "line6_대흥역", "name": "대흥역", "line": 6, "lat": 37.5476, "lng": 126.9430, "is_transfer": False},
            {"id": "line6_공덕역", "name": "공덕역", "line": 6, "lat": 37.5439, "lng": 126.9516, "is_transfer": True},
            {"id": "line6_효창공원앞역", "name": "효창공원앞역", "line": 6, "lat": 37.5393, "lng": 126.9614, "is_transfer": True},
            {"id": "line6_삼각지역", "name": "삼각지역", "line": 6, "lat": 37.5347, "lng": 126.9732, "is_transfer": True},
            {"id": "line6_녹사평역", "name": "녹사평역", "line": 6, "lat": 37.5345, "lng": 126.9876, "is_transfer": False},
            {"id": "line6_이태원역", "name": "이태원역", "line": 6, "lat": 37.5345, "lng": 126.9944, "is_transfer": False},
            {"id": "line6_한강진역", "name": "한강진역", "line": 6, "lat": 37.5399, "lng": 127.0014, "is_transfer": False},
            {"id": "line6_버티고개역", "name": "버티고개역", "line": 6, "lat": 37.5480, "lng": 127.0069, "is_transfer": False},
            {"id": "line6_약수역", "name": "약수역", "line": 6, "lat": 37.5545, "lng": 127.0103, "is_transfer": True},
            {"id": "line6_청구역", "name": "청구역", "line": 6, "lat": 37.5604, "lng": 127.0184, "is_transfer": True},
            {"id": "line6_신당역", "name": "신당역", "line": 6, "lat": 37.5659, "lng": 127.0175, "is_transfer": True},
            {"id": "line6_동묘앞역", "name": "동묘앞역", "line": 6, "lat": 37.5726, "lng": 127.0163, "is_transfer": True},
            {"id": "line6_창신역", "name": "창신역", "line": 6, "lat": 37.5791, "lng": 127.0150, "is_transfer": False},
            {"id": "line6_보문역", "name": "보문역", "line": 6, "lat": 37.5858, "lng": 127.0196, "is_transfer": False},
            {"id": "line6_안암역", "name": "안암역", "line": 6, "lat": 37.5858, "lng": 127.0286, "is_transfer": False},
            {"id": "line6_고려대역", "name": "고려대역", "line": 6, "lat": 37.5898, "lng": 127.0354, "is_transfer": False},
            {"id": "line6_월곡역", "name": "월곡역", "line": 6, "lat": 37.6005, "lng": 127.0388, "is_transfer": False},
            {"id": "line6_상월곡역", "name": "상월곡역", "line": 6, "lat": 37.6062, "lng": 127.0497, "is_transfer": False},
            {"id": "line6_돌곶이역", "name": "돌곶이역", "line": 6, "lat": 37.6100, "lng": 127.0570, "is_transfer": False},
            {"id": "line6_석계역", "name": "석계역", "line": 6, "lat": 37.6146, "lng": 127.0663, "is_transfer": True},
            {"id": "line6_태릉입구역", "name": "태릉입구역", "line": 6, "lat": 37.6172, "lng": 127.0745, "is_transfer": True},
            {"id": "line6_화랑대역", "name": "화랑대역", "line": 6, "lat": 37.6196, "lng": 127.0840, "is_transfer": False},
            {"id": "line6_봉화산역", "name": "봉화산역", "line": 6, "lat": 37.6177, "lng": 127.0919, "is_transfer": False},
            {"id": "line6_신내역", "name": "신내역", "line": 6, "lat": 37.6126, "lng": 127.1033, "is_transfer": False},

            # 7호선
            {"id": "line7_장암역", "name": "장암역", "line": 7, "lat": 37.7017, "lng": 127.0534, "is_transfer": False},
            {"id": "line7_도봉산역", "name": "도봉산역", "line": 7, "lat": 37.6896, "lng": 127.0445, "is_transfer": True},
            {"id": "line7_수락산역", "name": "수락산역", "line": 7, "lat": 37.6764, "lng": 127.0561, "is_transfer": False},
            {"id": "line7_마들역", "name": "마들역", "line": 7, "lat": 37.6659, "lng": 127.0576, "is_transfer": False},
            {"id": "line7_노원역", "name": "노원역", "line": 7, "lat": 37.6554, "lng": 127.0616, "is_transfer": True},
            {"id": "line7_중계역", "name": "중계역", "line": 7, "lat": 37.6442, "lng": 127.0637, "is_transfer": False},
            {"id": "line7_하계역", "name": "하계역", "line": 7, "lat": 37.6368, "lng": 127.0666, "is_transfer": False},
            {"id": "line7_공릉역", "name": "공릉역", "line": 7, "lat": 37.6252, "lng": 127.0732, "is_transfer": False},
            {"id": "line7_태릉입구역", "name": "태릉입구역", "line": 7, "lat": 37.6172, "lng": 127.0745, "is_transfer": True},
            {"id": "line7_먹골역", "name": "먹골역", "line": 7, "lat": 37.6100, "lng": 127.0774, "is_transfer": False},
            {"id": "line7_중화역", "name": "중화역", "line": 7, "lat": 37.6024, "lng": 127.0793, "is_transfer": False},
            {"id": "line7_상봉역", "name": "상봉역", "line": 7, "lat": 37.5966, "lng": 127.0847, "is_transfer": True},
            {"id": "line7_면목역", "name": "면목역", "line": 7, "lat": 37.5882, "lng": 127.0849, "is_transfer": False},
            {"id": "line7_사가정역", "name": "사가정역", "line": 7, "lat": 37.5798, "lng": 127.0859, "is_transfer": False},
            {"id": "line7_용마산역", "name": "용마산역", "line": 7, "lat": 37.5735, "lng": 127.0869, "is_transfer": False},
            {"id": "line7_중곡역", "name": "중곡역", "line": 7, "lat": 37.5654, "lng": 127.0843, "is_transfer": False},
            {"id": "line7_군자역", "name": "군자역", "line": 7, "lat": 37.5574, "lng": 127.0793, "is_transfer": True},
            {"id": "line7_어린이대공원역", "name": "어린이대공원역", "line": 7, "lat": 37.5482, "lng": 127.0739, "is_transfer": False},
            {"id": "line7_건대입구역", "name": "건대입구역", "line": 7, "lat": 37.5403, "lng": 127.0694, "is_transfer": True},
            {"id": "line7_뚝섬유원지역", "name": "뚝섬유원지역", "line": 7, "lat": 37.5317, "lng": 127.0685, "is_transfer": False},
            {"id": "line7_청담역", "name": "청담역", "line": 7, "lat": 37.5199, "lng": 127.0539, "is_transfer": False},
            {"id": "line7_강남구청역", "name": "강남구청역", "line": 7, "lat": 37.5173, "lng": 127.0410, "is_transfer": True},
            {"id": "line7_학동역", "name": "학동역", "line": 7, "lat": 37.5146, "lng": 127.0318, "is_transfer": False},
            {"id": "line7_논현역", "name": "논현역", "line": 7, "lat": 37.5108, "lng": 127.0218, "is_transfer": False},
            {"id": "line7_반포역", "name": "반포역", "line": 7, "lat": 37.5080, "lng": 127.0112, "is_transfer": False},
            {"id": "line7_고속터미널역", "name": "고속터미널역", "line": 7, "lat": 37.5049, "lng": 127.0051, "is_transfer": True},
            {"id": "line7_내방역", "name": "내방역", "line": 7, "lat": 37.4887, "lng": 126.9958, "is_transfer": False},
            {"id": "line7_이수역", "name": "이수역", "line": 7, "lat": 37.4858, "lng": 126.9821, "is_transfer": True},
            {"id": "line7_남성역", "name": "남성역", "line": 7, "lat": 37.4840, "lng": 126.9717, "is_transfer": False},
            {"id": "line7_숭실대입구역", "name": "숭실대입구역", "line": 7, "lat": 37.4969, "lng": 126.9538, "is_transfer": False},
            {"id": "line7_상도역", "name": "상도역", "line": 7, "lat": 37.5024, "lng": 126.9466, "is_transfer": False},
            {"id": "line7_장승배기역", "name": "장승배기역", "line": 7, "lat": 37.5069, "lng": 126.9390, "is_transfer": False},
            {"id": "line7_신대방삼거리역", "name": "신대방삼거리역", "line": 7, "lat": 37.5024, "lng": 126.9308, "is_transfer": False},
            {"id": "line7_보라매역", "name": "보라매역", "line": 7, "lat": 37.4986, "lng": 126.9205, "is_transfer": False},
            {"id": "line7_신풍역", "name": "신풍역", "line": 7, "lat": 37.5101, "lng": 126.9162, "is_transfer": False},
            {"id": "line7_대림역", "name": "대림역", "line": 7, "lat": 37.4932, "lng": 126.8958, "is_transfer": True},
            {"id": "line7_남구로역", "name": "남구로역", "line": 7, "lat": 37.4865, "lng": 126.8873, "is_transfer": False},
            {"id": "line7_가산디지털단지역", "name": "가산디지털단지역", "line": 7, "lat": 37.4816, "lng": 126.8827, "is_transfer": True},
            {"id": "line7_철산역", "name": "철산역", "line": 7, "lat": 37.4769, "lng": 126.8685, "is_transfer": False},
            {"id": "line7_광명사거리역", "name": "광명사거리역", "line": 7, "lat": 37.4739, "lng": 126.8582, "is_transfer": False},
            {"id": "line7_천왕역", "name": "천왕역", "line": 7, "lat": 37.4843, "lng": 126.8444, "is_transfer": False},
            {"id": "line7_온수역", "name": "온수역", "line": 7, "lat": 37.4922, "lng": 126.8231, "is_transfer": True},

            # 8호선
            {"id": "line8_암사역", "name": "암사역", "line": 8, "lat": 37.5509, "lng": 127.1277, "is_transfer": False},
            {"id": "line8_천호역", "name": "천호역", "line": 8, "lat": 37.5387, "lng": 127.1237, "is_transfer": True},
            {"id": "line8_강동구청역", "name": "강동구청역", "line": 8, "lat": 37.5304, "lng": 127.1192, "is_transfer": False},
            {"id": "line8_몽촌토성역", "name": "몽촌토성역", "line": 8, "lat": 37.5175, "lng": 127.1121, "is_transfer": False},
            {"id": "line8_잠실역", "name": "잠실역", "line": 8, "lat": 37.5132, "lng": 127.1001, "is_transfer": True},
            {"id": "line8_석촌역", "name": "석촌역", "line": 8, "lat": 37.5046, "lng": 127.1009, "is_transfer": False},
            {"id": "line8_송파역", "name": "송파역", "line": 8, "lat": 37.4971, "lng": 127.1053, "is_transfer": False},
            {"id": "line8_가락시장역", "name": "가락시장역", "line": 8, "lat": 37.4928, "lng": 127.1181, "is_transfer": True},
            {"id": "line8_문정역", "name": "문정역", "line": 8, "lat": 37.4869, "lng": 127.1227, "is_transfer": False},
            {"id": "line8_장지역", "name": "장지역", "line": 8, "lat": 37.4793, "lng": 127.1260, "is_transfer": False},
            {"id": "line8_복정역", "name": "복정역", "line": 8, "lat": 37.4701, "lng": 127.1269, "is_transfer": True},
            {"id": "line8_산성역", "name": "산성역", "line": 8, "lat": 37.4576, "lng": 127.1504, "is_transfer": False},
            {"id": "line8_남한산성입구역", "name": "남한산성입구역", "line": 8, "lat": 37.4507, "lng": 127.1596, "is_transfer": False},
            {"id": "line8_단대오거리역", "name": "단대오거리역", "line": 8, "lat": 37.4449, "lng": 127.1577, "is_transfer": False},
            {"id": "line8_신흥역", "name": "신흥역", "line": 8, "lat": 37.4402, "lng": 127.1502, "is_transfer": False},
            {"id": "line8_수진역", "name": "수진역", "line": 8, "lat": 37.4361, "lng": 127.1434, "is_transfer": False},
            {"id": "line8_모란역", "name": "모란역", "line": 8, "lat": 37.4323, "lng": 127.1290, "is_transfer": True},

            # 9호선
            {"id": "line9_개화역", "name": "개화역", "line": 9, "lat": 37.5726, "lng": 126.7976, "is_transfer": False},
            {"id": "line9_김포공항역", "name": "김포공항역", "line": 9, "lat": 37.5625, "lng": 126.8010, "is_transfer": True},
            {"id": "line9_공항시장역", "name": "공항시장역", "line": 9, "lat": 37.5590, "lng": 126.8081, "is_transfer": False},
            {"id": "line9_신방화역", "name": "신방화역", "line": 9, "lat": 37.5632, "lng": 126.8170, "is_transfer": False},
            {"id": "line9_마곡나루역", "name": "마곡나루역", "line": 9, "lat": 37.5672, "lng": 126.8276, "is_transfer": False},
            {"id": "line9_양천향교역", "name": "양천향교역", "line": 9, "lat": 37.5666, "lng": 126.8399, "is_transfer": False},
            {"id": "line9_가양역", "name": "가양역", "line": 9, "lat": 37.5614, "lng": 126.8536, "is_transfer": False},
            {"id": "line9_증미역", "name": "증미역", "line": 9, "lat": 37.5578, "lng": 126.8644, "is_transfer": False},
            {"id": "line9_등촌역", "name": "등촌역", "line": 9, "lat": 37.5514, "lng": 126.8718, "is_transfer": False},
            {"id": "line9_염창역", "name": "염창역", "line": 9, "lat": 37.5467, "lng": 126.8769, "is_transfer": False},
            {"id": "line9_신목동역", "name": "신목동역", "line": 9, "lat": 37.5399, "lng": 126.8799, "is_transfer": False},
            {"id": "line9_선유도역", "name": "선유도역", "line": 9, "lat": 37.5343, "lng": 126.8939, "is_transfer": False},
            {"id": "line9_당산역", "name": "당산역", "line": 9, "lat": 37.5348, "lng": 126.9023, "is_transfer": True},
            {"id": "line9_국회의사당역", "name": "국회의사당역", "line": 9, "lat": 37.5283, "lng": 126.9179, "is_transfer": False},
            {"id": "line9_여의도역", "name": "여의도역", "line": 9, "lat": 37.5216, "lng": 126.9242, "is_transfer": True},
            {"id": "line9_샛강역", "name": "샛강역", "line": 9, "lat": 37.5173, "lng": 126.9317, "is_transfer": False},
            {"id": "line9_노량진역", "name": "노량진역", "line": 9, "lat": 37.5132, "lng": 126.9426, "is_transfer": True},
            {"id": "line9_노들역", "name": "노들역", "line": 9, "lat": 37.5123, "lng": 126.9513, "is_transfer": False},
            {"id": "line9_흑석역", "name": "흑석역", "line": 9, "lat": 37.5086, "lng": 126.9637, "is_transfer": False},
            {"id": "line9_동작역", "name": "동작역", "line": 9, "lat": 37.5070, "lng": 126.9784, "is_transfer": True},
            {"id": "line9_구반포역", "name": "구반포역", "line": 9, "lat": 37.5053, "lng": 126.9896, "is_transfer": False},
            {"id": "line9_신반포역", "name": "신반포역", "line": 9, "lat": 37.5059, "lng": 126.9964, "is_transfer": False},
            {"id": "line9_고속터미널역", "name": "고속터미널역", "line": 9, "lat": 37.5049, "lng": 127.0051, "is_transfer": True},
            {"id": "line9_사평역", "name": "사평역", "line": 9, "lat": 37.5063, "lng": 127.0141, "is_transfer": False},
            {"id": "line9_신논현역", "name": "신논현역", "line": 9, "lat": 37.5048, "lng": 127.0251, "is_transfer": True},
            {"id": "line9_언주역", "name": "언주역", "line": 9, "lat": 37.5072, "lng": 127.0340, "is_transfer": False},
            {"id": "line9_선정릉역", "name": "선정릉역", "line": 9, "lat": 37.5103, "lng": 127.0432, "is_transfer": True},
            {"id": "line9_삼성중앙역", "name": "삼성중앙역", "line": 9, "lat": 37.5125, "lng": 127.0518, "is_transfer": False},
            {"id": "line9_봉은사역", "name": "봉은사역", "line": 9, "lat": 37.5141, "lng": 127.0613, "is_transfer": False},
            {"id": "line9_종합운동장역", "name": "종합운동장역", "line": 9, "lat": 37.5107, "lng": 127.0732, "is_transfer": True},
            {"id": "line9_삼전역", "name": "삼전역", "line": 9, "lat": 37.5076, "lng": 127.0857, "is_transfer": False},
            {"id": "line9_석촌고분역", "name": "석촌고분역", "line": 9, "lat": 37.5056, "lng": 127.0941, "is_transfer": False},
            {"id": "line9_석촌역", "name": "석촌역", "line": 9, "lat": 37.5046, "lng": 127.1009, "is_transfer": True},
            {"id": "line9_송파나루역", "name": "송파나루역", "line": 9, "lat": 37.5105, "lng": 127.1095, "is_transfer": False},
            {"id": "line9_한성백제역", "name": "한성백제역", "line": 9, "lat": 37.5178, "lng": 127.1123, "is_transfer": False},
            {"id": "line9_올림픽공원역", "name": "올림픽공원역", "line": 9, "lat": 37.5170, "lng": 127.1218, "is_transfer": True},
            {"id": "line9_둔촌오륜역", "name": "둔촌오륜역", "line": 9, "lat": 37.5203, "lng": 127.1308, "is_transfer": False},
            {"id": "line9_중앙보훈병원역", "name": "중앙보훈병원역", "line": 9, "lat": 37.5161, "lng": 127.1451, "is_transfer": False},

            # 신분당선 (line_id를 "shinbundang"으로 표시)
            {"id": "shinbundang_신사역", "name": "신사역", "line": "신분당", "lat": 37.5168, "lng": 127.0201, "is_transfer": True},
            {"id": "shinbundang_논현역", "name": "논현역", "line": "신분당", "lat": 37.5108, "lng": 127.0218, "is_transfer": False},
            {"id": "shinbundang_신논현역", "name": "신논현역", "line": "신분당", "lat": 37.5048, "lng": 127.0251, "is_transfer": True},
            {"id": "shinbundang_강남역", "name": "강남역", "line": "신분당", "lat": 37.4979, "lng": 127.0276, "is_transfer": True},
            {"id": "shinbundang_양재역", "name": "양재역", "line": "신분당", "lat": 37.4841, "lng": 127.0344, "is_transfer": True},
            {"id": "shinbundang_양재시민의숲역", "name": "양재시민의숲역", "line": "신분당", "lat": 37.4694, "lng": 127.0387, "is_transfer": False},
            {"id": "shinbundang_청계산입구역", "name": "청계산입구역", "line": "신분당", "lat": 37.4487, "lng": 127.0553, "is_transfer": False},
            {"id": "shinbundang_판교역", "name": "판교역", "line": "신분당", "lat": 37.3947, "lng": 127.1112, "is_transfer": False},
            {"id": "shinbundang_정자역", "name": "정자역", "line": "신분당", "lat": 37.3669, "lng": 127.1085, "is_transfer": False},
            {"id": "shinbundang_미금역", "name": "미금역", "line": "신분당", "lat": 37.3513, "lng": 127.1093, "is_transfer": False},
            {"id": "shinbundang_동천역", "name": "동천역", "line": "신분당", "lat": 37.3375, "lng": 127.1078, "is_transfer": False},
            {"id": "shinbundang_수지구청역", "name": "수지구청역", "line": "신분당", "lat": 37.3219, "lng": 127.0953, "is_transfer": False},
            {"id": "shinbundang_성복역", "name": "성복역", "line": "신분당", "lat": 37.3066, "lng": 127.0786, "is_transfer": False},
            {"id": "shinbundang_상현역", "name": "상현역", "line": "신분당", "lat": 37.2907, "lng": 127.0694, "is_transfer": False},
            {"id": "shinbundang_광교중앙역", "name": "광교중앙역", "line": "신분당", "lat": 37.2864, "lng": 127.0549, "is_transfer": False},
            {"id": "shinbundang_광교역", "name": "광교역", "line": "신분당", "lat": 37.2792, "lng": 127.0461, "is_transfer": False},
        ]

    def _get_builtin_edges(self) -> List[Dict]:
        """내장 엣지 데이터"""
        # 노선별 역 순서 정의
        line_sequences = {
            1: ["소요산역", "동두천역", "의정부역", "회룡역", "도봉산역", "창동역",
                "석계역", "광운대역", "청량리역", "동대문역", "종로3가역", "종각역",
                "시청역", "서울역", "남영역", "용산역", "영등포역", "신도림역", "구로역", "인천역"],
            2: ["시청역", "을지로입구역", "을지로3가역", "을지로4가역", "동대문역사문화공원역",
                "신당역", "상왕십리역", "왕십리역", "한양대역", "뚝섬역", "성수역",
                "건대입구역", "구의역", "강변역", "잠실나루역", "잠실역", "잠실새내역",
                "종합운동장역", "삼성역", "선릉역", "역삼역", "강남역", "교대역", "서초역",
                "방배역", "사당역", "낙성대역", "서울대입구역", "봉천역", "신림역",
                "신대방역", "구로디지털단지역", "대림역", "신도림역", "문래역",
                "영등포구청역", "당산역", "합정역", "홍대입구역", "신촌역", "이대역",
                "아현역", "충정로역"],
            3: ["대화역", "연신내역", "불광역", "녹번역", "홍제역", "무악재역", "독립문역",
                "경복궁역", "안국역", "종로3가역", "을지로3가역", "충무로역", "동대입구역",
                "약수역", "금호역", "옥수역", "압구정역", "신사역", "잠원역", "고속터미널역",
                "교대역", "남부터미널역", "양재역", "매봉역", "도곡역", "대치역", "학여울역",
                "대청역", "일원역", "수서역", "오금역"],
            4: ["당고개역", "상계역", "노원역", "창동역", "쌍문역", "수유역", "미아역",
                "미아사거리역", "길음역", "성신여대입구역", "한성대입구역", "혜화역",
                "동대문역", "동대문역사문화공원역", "충무로역", "명동역", "회현역", "서울역",
                "숙대입구역", "삼각지역", "신용산역", "이촌역", "동작역", "총신대입구역",
                "사당역", "남태령역", "선바위역", "경마공원역", "대공원역", "과천역",
                "정부과천청사역", "인덕원역", "평촌역", "범계역", "금정역", "안산역", "오이도역"],
            5: ["방화역", "개화산역", "김포공항역", "송정역", "마곡역", "발산역", "우장산역",
                "화곡역", "까치산역", "신정역", "목동역", "오목교역", "양평역", "영등포구청역",
                "영등포시장역", "신길역", "여의도역", "여의나루역", "마포역", "공덕역",
                "애오개역", "충정로역", "서대문역", "광화문역", "종로3가역", "을지로4가역",
                "동대문역사문화공원역", "청구역", "신금호역", "행당역", "왕십리역", "마장역",
                "답십리역", "장한평역", "군자역", "아차산역", "광나루역", "천호역", "강동역",
                "길동역", "굽은다리역", "명일역", "고덕역", "상일동역"],
            6: ["응암역", "역촌역", "불광역", "독바위역", "연신내역", "구산역", "새절역",
                "증산역", "디지털미디어시티역", "월드컵경기장역", "마포구청역", "망원역",
                "합정역", "상수역", "광흥창역", "대흥역", "공덕역", "효창공원앞역", "삼각지역",
                "녹사평역", "이태원역", "한강진역", "버티고개역", "약수역", "청구역", "신당역",
                "동묘앞역", "창신역", "보문역", "안암역", "고려대역", "월곡역", "상월곡역",
                "돌곶이역", "석계역", "태릉입구역", "화랑대역", "봉화산역", "신내역"],
            7: ["장암역", "도봉산역", "수락산역", "마들역", "노원역", "중계역", "하계역",
                "공릉역", "태릉입구역", "먹골역", "중화역", "상봉역", "면목역", "사가정역",
                "용마산역", "중곡역", "군자역", "어린이대공원역", "건대입구역", "뚝섬유원지역",
                "청담역", "강남구청역", "학동역", "논현역", "반포역", "고속터미널역", "내방역",
                "이수역", "남성역", "숭실대입구역", "상도역", "장승배기역", "신대방삼거리역",
                "보라매역", "신풍역", "대림역", "남구로역", "가산디지털단지역", "철산역",
                "광명사거리역", "천왕역", "온수역"],
            8: ["암사역", "천호역", "강동구청역", "몽촌토성역", "잠실역", "석촌역", "송파역",
                "가락시장역", "문정역", "장지역", "복정역", "산성역", "남한산성입구역",
                "단대오거리역", "신흥역", "수진역", "모란역"],
            9: ["개화역", "김포공항역", "공항시장역", "신방화역", "마곡나루역", "양천향교역",
                "가양역", "증미역", "등촌역", "염창역", "신목동역", "선유도역", "당산역",
                "국회의사당역", "여의도역", "샛강역", "노량진역", "노들역", "흑석역", "동작역",
                "구반포역", "신반포역", "고속터미널역", "사평역", "신논현역", "언주역",
                "선정릉역", "삼성중앙역", "봉은사역", "종합운동장역", "삼전역", "석촌고분역",
                "석촌역", "송파나루역", "한성백제역", "올림픽공원역", "둔촌오륜역", "중앙보훈병원역"],
        }

        # 신분당선 별도 처리 (prefix가 다름)
        shinbundang_sequence = [
            "신사역", "논현역", "신논현역", "강남역", "양재역", "양재시민의숲역",
            "청계산입구역", "판교역", "정자역", "미금역", "동천역", "수지구청역",
            "성복역", "상현역", "광교중앙역", "광교역"
        ]

        edges = []
        for line, stations in line_sequences.items():
            for i in range(len(stations) - 1):
                edges.append({
                    "from": f"line{line}_{stations[i]}",
                    "to": f"line{line}_{stations[i+1]}",
                    "line": line,
                    "minutes": 2
                })

        # 신분당선 엣지 추가
        for i in range(len(shinbundang_sequence) - 1):
            edges.append({
                "from": f"shinbundang_{shinbundang_sequence[i]}",
                "to": f"shinbundang_{shinbundang_sequence[i+1]}",
                "line": "신분당",
                "minutes": 2
            })

        # 2호선 순환 연결
        edges.append({"from": "line2_충정로역", "to": "line2_시청역", "line": 2, "minutes": 2})

        return edges

    def _get_builtin_transfers(self) -> List[Dict]:
        """내장 환승 데이터"""
        # 숫자 노선 간 환승
        transfer_stations = {
            "시청역": [(1, 2)],
            "동대문역": [(1, 4)],
            "종로3가역": [(1, 3), (1, 5), (3, 5)],
            "서울역": [(1, 4)],
            "용산역": [(1, 4)],
            "신도림역": [(1, 2)],
            "창동역": [(1, 4)],
            "석계역": [(1, 6)],
            "도봉산역": [(1, 7)],
            "노량진역": [(1, 9)],
            "을지로3가역": [(2, 3)],
            "을지로4가역": [(2, 5)],
            "동대문역사문화공원역": [(2, 4), (2, 5), (4, 5)],
            "신당역": [(2, 6)],
            "왕십리역": [(2, 5)],
            "건대입구역": [(2, 7)],
            "잠실역": [(2, 8)],
            "종합운동장역": [(2, 9)],
            "교대역": [(2, 3)],
            "사당역": [(2, 4)],
            "대림역": [(2, 7)],
            "영등포구청역": [(2, 5)],
            "당산역": [(2, 9)],
            "합정역": [(2, 6)],
            "충정로역": [(2, 5)],
            "연신내역": [(3, 6)],
            "불광역": [(3, 6)],
            "충무로역": [(3, 4)],
            "약수역": [(3, 6)],
            "고속터미널역": [(3, 7), (3, 9), (7, 9)],
            "오금역": [(3, 5)],
            "노원역": [(4, 7)],
            "삼각지역": [(4, 6)],
            "동작역": [(4, 9)],
            "총신대입구역": [(4, 7)],
            "김포공항역": [(5, 9)],
            "신길역": [(5, 7)],
            "공덕역": [(5, 6)],
            "여의도역": [(5, 9)],
            "청구역": [(5, 6)],
            "군자역": [(5, 7)],
            "천호역": [(5, 8)],
            "올림픽공원역": [(5, 9)],
            "태릉입구역": [(6, 7)],
            "이수역": [(4, 7)],
            "가산디지털단지역": [(7, 1)],
            "온수역": [(7, 1)],
            "가락시장역": [(8, 3)],
            "석촌역": [(8, 9)],
        }

        transfers = []
        for station, lines in transfer_stations.items():
            for from_line, to_line in lines:
                transfers.append({
                    "station": station,
                    "from": f"line{from_line}_{station}",
                    "to": f"line{to_line}_{station}",
                    "from_line": from_line,
                    "to_line": to_line,
                    "minutes": 3
                })
                transfers.append({
                    "station": station,
                    "from": f"line{to_line}_{station}",
                    "to": f"line{from_line}_{station}",
                    "from_line": to_line,
                    "to_line": from_line,
                    "minutes": 3
                })

        # 신분당선 환승 (별도 처리 - prefix가 다름)
        shinbundang_transfers = [
            # 신사역: 3호선 ↔ 신분당선
            ("신사역", "line3_신사역", "shinbundang_신사역"),
            # 신논현역: 9호선 ↔ 신분당선
            ("신논현역", "line9_신논현역", "shinbundang_신논현역"),
            # 강남역: 2호선 ↔ 신분당선
            ("강남역", "line2_강남역", "shinbundang_강남역"),
            # 양재역: 3호선 ↔ 신분당선
            ("양재역", "line3_양재역", "shinbundang_양재역"),
        ]

        for station, from_id, to_id in shinbundang_transfers:
            transfers.append({
                "station": station,
                "from": from_id,
                "to": to_id,
                "minutes": 3
            })
            transfers.append({
                "station": station,
                "from": to_id,
                "to": from_id,
                "minutes": 3
            })

        # 선정릉역: 분당선(수인분당선)은 현재 미포함이므로 9호선만 있음

        return transfers


# 편의 함수
def create_commute_calculator(data_dir: Optional[str] = None) -> SeoulSubwayCommute:
    """통근시간 계산기 생성"""
    return SeoulSubwayCommute(data_dir)


# 테스트
if __name__ == "__main__":
    print("=" * 60)
    print("서울 지하철 통근시간 계산 모듈 테스트")
    print("=" * 60)

    # 인스턴스 생성 (내장 데이터 사용)
    commute = SeoulSubwayCommute()

    # 통계
    stats = commute.get_stats()
    print(f"\n로드된 데이터: {stats['stations']}개 역, {stats['edges']}개 구간")

    # 역명으로 계산
    print("\n[역명 기반 계산]")
    result = commute.calculate("강남역", "건대입구역")
    if result:
        print(f"강남역 → 건대입구역: {result['text']} (실제 {result['minutes']}분)")

    # 좌표로 계산
    print("\n[좌표 기반 계산]")
    result = commute.calculate_by_coords(37.5430, 127.0716, 37.4979, 127.0276)
    if result:
        print(f"화양동 → 강남역: {result['text']} (실제 {result['minutes']}분)")

    # 공고 필터링
    print("\n[공고 필터링]")
    jobs = [
        {"id": 1, "title": "강남 개발자", "lat": 37.5006, "lng": 127.0365},
        {"id": 2, "title": "홍대 디자이너", "lat": 37.5563, "lng": 126.9237},
        {"id": 3, "title": "잠실 마케터", "lat": 37.5132, "lng": 127.1001},
    ]

    filtered = commute.filter_jobs(jobs, origin="건대입구역", max_minutes=40)
    print(f"건대입구역에서 40분 이내: {len(filtered)}건")
    for job in filtered:
        print(f"  - {job['title']}: {job['travel_time_text']}")

    print("\n" + "=" * 60)
    print("테스트 완료!")
    print("=" * 60)
