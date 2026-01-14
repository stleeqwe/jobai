"""
기존 jobs 데이터에 nearest_station, station_walk_minutes 필드 추가

V6 아키텍처용 마이그레이션 스크립트
- location_full (회사주소)를 기반으로 가장 가까운 지하철역 계산
- nearest_station: 역 이름 (예: "강남역")
- station_walk_minutes: 도보 시간 (분)
"""
import sys
sys.path.insert(0, '/Users/stlee/Desktop/jobbot/jobai/backend')

from google.cloud import firestore
from app.services.seoul_subway_commute import SeoulSubwayCommute


def migrate_nearest_station():
    """기존 데이터에 nearest_station 필드 추가"""

    # Firestore 클라이언트
    db = firestore.Client(project="jobchat-1768149763")
    jobs_ref = db.collection("jobs")

    # 지하철 모듈 초기화
    print("지하철 모듈 초기화 중...")
    subway = SeoulSubwayCommute()
    if not subway.is_initialized():
        print("지하철 모듈 초기화 실패!")
        return

    stats = subway.get_stats()
    print(f"지하철 데이터: {stats['stations']}개 역, {stats['edges']}개 구간")

    # 모든 jobs 가져오기
    print("\njobs 컬렉션 조회 중...")
    docs = list(jobs_ref.stream())
    print(f"총 {len(docs)}건의 문서")

    updated = 0
    already_has = 0
    no_address = 0
    parse_failed = 0
    no_station = 0

    for i, doc in enumerate(docs):
        data = doc.to_dict()
        job_id = doc.id

        # 이미 nearest_station이 있는 경우 스킵
        if data.get("nearest_station"):
            already_has += 1
            continue

        # location_full 또는 company_address 확인
        address = data.get("location_full") or data.get("company_address", "")
        if not address:
            no_address += 1
            continue

        # 좌표 파싱
        coords = subway._parse_location(address)
        if not coords:
            parse_failed += 1
            continue

        lat, lng = coords

        # 가장 가까운 역 찾기
        station_id, walk_minutes = subway._find_nearest_station(lat, lng)
        if not station_id:
            no_station += 1
            continue

        station_info = subway.stations.get(station_id, {})
        nearest_station = station_info.get("name", "")

        if nearest_station:
            # Firestore 업데이트
            doc.reference.update({
                "nearest_station": nearest_station,
                "station_walk_minutes": walk_minutes
            })
            updated += 1

            if updated % 50 == 0:
                print(f"진행: {updated}건 업데이트 ({i+1}/{len(docs)})")

    print(f"\n=== 마이그레이션 완료 ===")
    print(f"업데이트: {updated}건")
    print(f"이미 있음: {already_has}건")
    print(f"주소 없음: {no_address}건")
    print(f"좌표 파싱 실패: {parse_failed}건")
    print(f"가까운 역 없음: {no_station}건")


if __name__ == "__main__":
    migrate_nearest_station()
