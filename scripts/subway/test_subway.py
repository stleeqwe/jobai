#!/usr/bin/env python3
"""
지하철 통근시간 계산 테스트 스크립트 (독립 실행)

사용법:
python3 scripts/subway/test_subway.py
"""

import json
import heapq
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

project_root = Path(__file__).parent.parent.parent
DATA_DIR = project_root / "backend" / "app" / "data" / "subway"


class SubwayGraphTest:
    """테스트용 그래프 클래스"""

    def __init__(self):
        self.adjacency: Dict[str, List[Tuple[str, int]]] = {}
        self.stations: Dict[str, Dict] = {}
        self.station_coords: List[Tuple[float, float, str]] = []
        self.name_to_ids: Dict[str, List[str]] = {}

    def load_from_json(self, data_dir: str) -> bool:
        data_path = Path(data_dir)

        try:
            # 역 정보 로드
            with open(data_path / "stations.json", encoding="utf-8") as f:
                stations_data = json.load(f)

            for s in stations_data:
                station_id = s["id"]
                self.stations[station_id] = s
                self.adjacency[station_id] = []

                lat, lng = s.get("lat", 0), s.get("lng", 0)
                if lat and lng:
                    self.station_coords.append((lat, lng, station_id))

                name = s.get("name", "")
                if name not in self.name_to_ids:
                    self.name_to_ids[name] = []
                self.name_to_ids[name].append(station_id)

            # 엣지 로드
            with open(data_path / "edges.json", encoding="utf-8") as f:
                edges_data = json.load(f)

            for e in edges_data:
                from_id, to_id = e["from"], e["to"]
                minutes = e.get("minutes", 2)

                if from_id in self.adjacency:
                    self.adjacency[from_id].append((to_id, minutes))
                if to_id not in self.adjacency:
                    self.adjacency[to_id] = []
                self.adjacency[to_id].append((from_id, minutes))

            # 환승 엣지 로드
            with open(data_path / "transfers.json", encoding="utf-8") as f:
                transfers_data = json.load(f)

            for t in transfers_data:
                from_id, to_id = t["from"], t["to"]
                minutes = t.get("minutes", 3)

                if from_id in self.adjacency:
                    self.adjacency[from_id].append((to_id, minutes))

            return True

        except Exception as e:
            print(f"로드 오류: {e}")
            return False

    def dijkstra(self, start: str, end: str) -> Tuple[Optional[int], List[str]]:
        if start not in self.adjacency or end not in self.adjacency:
            return None, []

        if start == end:
            return 0, [start]

        distances = {start: 0}
        previous = {start: None}
        heap = [(0, start)]
        visited = set()

        while heap:
            current_dist, current = heapq.heappop(heap)

            if current in visited:
                continue
            visited.add(current)

            if current == end:
                path = []
                node = end
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

    def find_nearest_station(self, lat: float, lng: float) -> Tuple[Optional[str], int]:
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

        walking_minutes = int(min_dist / 80) + 1  # 80m/분
        return nearest_id, min(walking_minutes, 30)

    @staticmethod
    def _haversine_distance(lat1, lng1, lat2, lng2) -> float:
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lng2 - lng1)

        a = (math.sin(delta_phi / 2) ** 2 +
             math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def calculate_travel_time(self, from_lat, from_lng, to_lat, to_lng) -> Optional[int]:
        from_station, from_walk = self.find_nearest_station(from_lat, from_lng)
        if not from_station:
            return None

        to_station, to_walk = self.find_nearest_station(to_lat, to_lng)
        if not to_station:
            return None

        if from_station == to_station:
            return min(from_walk, to_walk)

        subway_time, _ = self.dijkstra(from_station, to_station)
        if subway_time is None:
            return None

        return from_walk + subway_time + to_walk + 5  # +5분 대기


def test_graph_loading():
    print("=" * 50)
    print("1. 그래프 로딩 테스트")
    print("=" * 50)

    graph = SubwayGraphTest()
    success = graph.load_from_json(str(DATA_DIR))

    print(f"로딩 성공: {success}")
    print(f"역 수: {len(graph.stations)}")
    print(f"인접 리스트 크기: {sum(len(v) for v in graph.adjacency.values())}")

    return graph if success else None


def test_nearest_station(graph):
    print("\n" + "=" * 50)
    print("2. 최근접 역 찾기 테스트")
    print("=" * 50)

    test_cases = [
        ("강남역 근처", 37.4979, 127.0276),
        ("건대입구역 근처", 37.5403, 127.0694),
        ("화양동", 37.5430, 127.0716),
        ("역삼동", 37.5006, 127.0365),
        ("서울역 근처", 37.5547, 126.9707),
    ]

    for name, lat, lng in test_cases:
        station_id, walk_min = graph.find_nearest_station(lat, lng)
        station = graph.stations.get(station_id, {})
        print(f"{name} → {station.get('name', '?')} ({station.get('line', '?')}호선), 도보 {walk_min}분")


def test_dijkstra(graph):
    print("\n" + "=" * 50)
    print("3. 최단경로 (Dijkstra) 테스트")
    print("=" * 50)

    test_routes = [
        ("line2_강남역", "line2_건대입구역"),
        ("line2_강남역", "line1_서울역"),
        ("line2_홍대입구역", "line2_잠실역"),
        ("line3_경복궁역", "line2_역삼역"),
        ("line7_건대입구역", "line5_광화문역"),
    ]

    for from_id, to_id in test_routes:
        minutes, path = graph.dijkstra(from_id, to_id)
        from_name = graph.stations.get(from_id, {}).get("name", from_id)
        to_name = graph.stations.get(to_id, {}).get("name", to_id)

        if minutes is not None:
            transfers = len(set(p.split("_")[0] for p in path)) - 1
            print(f"{from_name} → {to_name}: {minutes}분 (환승 {transfers}회)")
        else:
            print(f"{from_name} → {to_name}: 경로 없음")


def test_travel_time(graph):
    print("\n" + "=" * 50)
    print("4. 좌표 간 이동시간 계산 테스트")
    print("=" * 50)

    test_cases = [
        ("화양동 → 강남역", 37.5430, 127.0716, 37.4979, 127.0276),
        ("홍대 → 잠실", 37.5573, 126.9236, 37.5132, 127.1001),
        ("서울역 → 역삼", 37.5547, 126.9707, 37.5006, 127.0365),
        ("건대 → 광화문", 37.5403, 127.0694, 37.5759, 126.9769),
    ]

    for name, from_lat, from_lng, to_lat, to_lng in test_cases:
        total = graph.calculate_travel_time(from_lat, from_lng, to_lat, to_lng)
        if total:
            rounded = round(total / 10) * 10
            rounded = max(10, rounded)
            print(f"{name}: {total}분 → 약 {rounded}분")
        else:
            print(f"{name}: 계산 실패")


def test_filter_jobs(graph):
    print("\n" + "=" * 50)
    print("5. 공고 필터링 테스트")
    print("=" * 50)

    # 테스트용 더미 공고
    test_jobs = [
        {"id": "job1", "title": "강남 개발자", "lat": 37.5006, "lng": 127.0365},
        {"id": "job2", "title": "홍대 디자이너", "lat": 37.5563, "lng": 126.9237},
        {"id": "job3", "title": "잠실 마케터", "lat": 37.5132, "lng": 127.1001},
        {"id": "job4", "title": "종로 기획자", "lat": 37.5713, "lng": 126.9916},
        {"id": "job5", "title": "구로 엔지니어", "lat": 37.4851, "lng": 126.9014},
    ]

    # 건대입구역 좌표
    origin_lat, origin_lng = 37.5403, 127.0694
    max_minutes = 60

    print(f"출발지: 건대입구역 ({origin_lat}, {origin_lng})")
    print(f"최대 통근시간: {max_minutes}분\n")

    results = []
    for job in test_jobs:
        travel_time = graph.calculate_travel_time(
            origin_lat, origin_lng,
            job["lat"], job["lng"]
        )
        if travel_time and travel_time <= max_minutes:
            rounded = round(travel_time / 10) * 10
            rounded = max(10, rounded)
            results.append({
                **job,
                "travel_time_minutes": travel_time,
                "travel_time_text": f"약 {rounded}분"
            })

    results.sort(key=lambda x: x["travel_time_minutes"])

    print(f"결과: {len(results)}건 / {len(test_jobs)}건")
    for job in results:
        print(f"  - {job['title']}: {job['travel_time_text']} (실제 {job['travel_time_minutes']}분)")


def main():
    print("서울 지하철 통근시간 계산 테스트\n")

    # 1. 그래프 로딩
    graph = test_graph_loading()
    if not graph:
        print("\n그래프 로딩 실패! 먼저 샘플 데이터를 생성하세요:")
        print("python3 scripts/subway/generate_sample_data.py")
        return

    # 2. 최근접 역
    test_nearest_station(graph)

    # 3. Dijkstra
    test_dijkstra(graph)

    # 4. 좌표 간 이동시간
    test_travel_time(graph)

    # 5. 공고 필터링
    test_filter_jobs(graph)

    print("\n" + "=" * 50)
    print("테스트 완료!")
    print("=" * 50)


if __name__ == "__main__":
    main()
