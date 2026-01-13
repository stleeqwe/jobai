#!/usr/bin/env python3
"""
서울 지하철 그래프 빌드 스크립트

raw 데이터를 파싱하여 그래프 구조를 생성합니다:
- stations.json: 역 정보 (이름, 호선, 좌표)
- edges.json: 역간 이동시간
- transfers.json: 환승 시간

사용법:
python scripts/subway/build_graph.py
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

# 프로젝트 루트
project_root = Path(__file__).parent.parent.parent
DATA_DIR = project_root / "backend" / "app" / "data" / "subway"
RAW_DIR = DATA_DIR / "raw"


def load_raw_data():
    """raw 데이터 로드"""
    data = {}

    # 역 좌표
    coords_file = RAW_DIR / "raw_station_coords.json"
    if coords_file.exists():
        with open(coords_file, encoding="utf-8") as f:
            data["coords"] = json.load(f)
        print(f"역 좌표: {len(data['coords'])}건 로드")

    # 역간 시간
    time_file = RAW_DIR / "raw_station_time.json"
    if time_file.exists():
        with open(time_file, encoding="utf-8") as f:
            data["times"] = json.load(f)
        print(f"역간 시간: {len(data['times'])}건 로드")

    # 환승 시간
    transfer_file = RAW_DIR / "raw_transfer_time.json"
    if transfer_file.exists():
        with open(transfer_file, encoding="utf-8") as f:
            data["transfers"] = json.load(f)
        print(f"환승 시간: {len(data['transfers'])}건 로드")

    return data


def normalize_station_name(name: str) -> str:
    """역명 정규화"""
    # 괄호 제거: "서울역(1호선)" -> "서울역"
    if "(" in name:
        name = name.split("(")[0]
    # 공백 제거
    name = name.strip()
    # "역" 접미사 통일
    if not name.endswith("역") and not name.endswith("입구"):
        name = name + "역"
    return name


def normalize_line(line) -> int:
    """호선 번호 정규화"""
    if isinstance(line, int):
        return line
    if isinstance(line, str):
        # "2호선" -> 2
        line = line.replace("호선", "").strip()
        try:
            return int(line)
        except ValueError:
            # 신분당선, 경의중앙선 등은 제외 (MVP는 1-8호선)
            return 0
    return 0


def build_stations(coords_data: list) -> dict:
    """역 정보 빌드"""
    stations = {}

    for item in coords_data:
        line = normalize_line(item.get("호선", item.get("line", 0)))
        if line < 1 or line > 8:
            continue  # 1-8호선만

        name = item.get("역명", item.get("station_name", ""))
        name = normalize_station_name(name)

        lat = float(item.get("위도", item.get("lat", 0)))
        lng = float(item.get("경도", item.get("lng", 0)))

        if lat == 0 or lng == 0:
            continue

        station_id = f"line{line}_{name}"
        stations[station_id] = {
            "id": station_id,
            "name": name,
            "line": line,
            "lat": lat,
            "lng": lng,
            "is_transfer": False
        }

    return stations


def build_edges(time_data: list, stations: dict) -> list:
    """역간 이동시간 엣지 빌드"""
    edges = []
    station_names = {s["name"] for s in stations.values()}

    for item in time_data:
        line = normalize_line(item.get("호선", item.get("line", 0)))
        if line < 1 or line > 8:
            continue

        # 역명 파싱 (데이터 형식에 따라 다름)
        from_name = item.get("출발역명", item.get("역명", ""))
        to_name = item.get("도착역명", "")

        # 일부 데이터는 "역명"만 있고, 순서대로 나열됨
        if not to_name:
            continue

        from_name = normalize_station_name(from_name)
        to_name = normalize_station_name(to_name)

        # 시간 파싱
        time_val = item.get("운행시간", item.get("소요시간", item.get("HM", 0)))
        if isinstance(time_val, str):
            time_val = time_val.replace("분", "").strip()
            try:
                time_val = int(float(time_val))
            except ValueError:
                time_val = 2  # 기본값

        if time_val <= 0:
            time_val = 2  # 최소 2분

        from_id = f"line{line}_{from_name}"
        to_id = f"line{line}_{to_name}"

        if from_id in stations and to_id in stations:
            edges.append({
                "from": from_id,
                "to": to_id,
                "line": line,
                "minutes": time_val,
                "is_transfer": False
            })

    return edges


def build_transfers(transfer_data: list, stations: dict) -> list:
    """환승 정보 빌드"""
    transfers = []
    transfer_stations = set()

    for item in transfer_data:
        station_name = item.get("환승역명", item.get("역명", ""))
        station_name = normalize_station_name(station_name)

        from_line = normalize_line(item.get("출발호선", item.get("호선", 0)))
        to_line = normalize_line(item.get("도착호선", item.get("환승노선", 0)))

        if from_line < 1 or from_line > 8 or to_line < 1 or to_line > 8:
            continue
        if from_line == to_line:
            continue

        # 환승 시간 (초 -> 분)
        time_val = item.get("환승소요시간", item.get("소요시간", 180))
        if isinstance(time_val, str):
            time_val = time_val.replace("초", "").replace("분", "").strip()
            try:
                time_val = int(float(time_val))
            except ValueError:
                time_val = 180

        # 초 단위면 분으로 변환
        if time_val > 60:
            time_val = (time_val + 59) // 60  # 올림

        if time_val <= 0:
            time_val = 3  # 최소 3분

        from_id = f"line{from_line}_{station_name}"
        to_id = f"line{to_line}_{station_name}"

        if from_id in stations and to_id in stations:
            transfers.append({
                "station": station_name,
                "from": from_id,
                "to": to_id,
                "from_line": from_line,
                "to_line": to_line,
                "minutes": time_val
            })
            transfer_stations.add(from_id)
            transfer_stations.add(to_id)

    # 환승역 마킹
    for station_id in transfer_stations:
        if station_id in stations:
            stations[station_id]["is_transfer"] = True

    return transfers


def validate_graph(stations: dict, edges: list, transfers: list):
    """그래프 연결성 검증"""
    print("\n=== 그래프 검증 ===")

    # 인접 리스트 구축
    adjacency = defaultdict(list)
    for edge in edges:
        adjacency[edge["from"]].append(edge["to"])
        adjacency[edge["to"]].append(edge["from"])

    for transfer in transfers:
        adjacency[transfer["from"]].append(transfer["to"])
        adjacency[transfer["to"]].append(transfer["from"])

    # BFS로 연결성 확인
    if not stations:
        print("경고: 역 데이터가 없습니다!")
        return False

    start = next(iter(stations.keys()))
    visited = {start}
    queue = [start]

    while queue:
        node = queue.pop(0)
        for neighbor in adjacency[node]:
            if neighbor not in visited and neighbor in stations:
                visited.add(neighbor)
                queue.append(neighbor)

    coverage = len(visited) / len(stations) * 100
    print(f"연결된 역: {len(visited)}/{len(stations)} ({coverage:.1f}%)")

    if len(visited) < len(stations):
        disconnected = set(stations.keys()) - visited
        print(f"연결 안 된 역 (샘플): {list(disconnected)[:5]}")

    # 호선별 통계
    line_stats = defaultdict(int)
    for s in stations.values():
        line_stats[s["line"]] += 1

    print("\n호선별 역 수:")
    for line in sorted(line_stats.keys()):
        print(f"  {line}호선: {line_stats[line]}개")

    return coverage > 90


def save_graph(stations: dict, edges: list, transfers: list):
    """그래프 저장"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # stations.json
    with open(DATA_DIR / "stations.json", "w", encoding="utf-8") as f:
        json.dump(list(stations.values()), f, ensure_ascii=False, indent=2)
    print(f"\n저장: stations.json ({len(stations)}개)")

    # edges.json
    with open(DATA_DIR / "edges.json", "w", encoding="utf-8") as f:
        json.dump(edges, f, ensure_ascii=False, indent=2)
    print(f"저장: edges.json ({len(edges)}개)")

    # transfers.json
    with open(DATA_DIR / "transfers.json", "w", encoding="utf-8") as f:
        json.dump(transfers, f, ensure_ascii=False, indent=2)
    print(f"저장: transfers.json ({len(transfers)}개)")


def main():
    print("서울 지하철 그래프 빌드 시작...\n")

    # raw 데이터 로드
    raw_data = load_raw_data()

    if not raw_data.get("coords"):
        print("\n오류: raw 데이터가 없습니다.")
        print("먼저 다음 중 하나를 실행하세요:")
        print("1. python scripts/subway/download_data.py (API 키 필요)")
        print("2. python scripts/subway/generate_sample_data.py (샘플 데이터)")
        return

    # 그래프 빌드
    stations = build_stations(raw_data.get("coords", []))
    print(f"\n역 파싱 완료: {len(stations)}개")

    edges = build_edges(raw_data.get("times", []), stations)
    print(f"엣지 파싱 완료: {len(edges)}개")

    transfers = build_transfers(raw_data.get("transfers", []), stations)
    print(f"환승 파싱 완료: {len(transfers)}개")

    # 검증
    if validate_graph(stations, edges, transfers):
        save_graph(stations, edges, transfers)
        print("\n빌드 완료!")
    else:
        print("\n경고: 그래프 연결성이 낮습니다. 데이터를 확인하세요.")
        save_graph(stations, edges, transfers)


if __name__ == "__main__":
    main()
