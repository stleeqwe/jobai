#!/usr/bin/env python3
"""
서울 지하철 공공데이터 다운로드 스크립트

공공데이터포털(data.go.kr)에서 다음 데이터를 다운로드합니다:
1. 역간 거리 및 소요시간 (15119345)
2. 환승역 소요시간 (15044419)
3. 역 좌표 (15099316)

사용법:
1. data.go.kr에서 API 키 발급
2. 환경변수 설정: export PUBLIC_DATA_API_KEY=your_key
3. 실행: python scripts/subway/download_data.py
"""

import os
import sys
import json
import asyncio
from pathlib import Path

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    import httpx
except ImportError:
    print("httpx 설치 필요: pip install httpx")
    sys.exit(1)


# 공공데이터 API 엔드포인트
DATA_SOURCES = {
    "station_coords": {
        "name": "역 좌표 (1-8호선)",
        "url": "https://api.odcloud.kr/api/15099316/v1/uddi:fa3d6ea8-53b7-4284-ae5b-24706d3ad8cf",
        "output": "raw_station_coords.json"
    },
    "station_time": {
        "name": "역간 소요시간",
        "url": "https://api.odcloud.kr/api/15119345/v1/uddi:aeea2d30-c094-4dcf-924c-22f21cf65f29",
        "output": "raw_station_time.json"
    },
    "transfer_time": {
        "name": "환승 소요시간",
        "url": "https://api.odcloud.kr/api/15044419/v1/uddi:c6a3a4c3-9f01-49da-9a64-8ab8e4a2f4c5",
        "output": "raw_transfer_time.json"
    }
}

OUTPUT_DIR = project_root / "backend" / "app" / "data" / "subway" / "raw"


async def download_data(api_key: str):
    """공공데이터 API에서 데이터 다운로드"""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=30.0) as client:
        for key, config in DATA_SOURCES.items():
            print(f"\n다운로드 중: {config['name']}...")

            all_data = []
            page = 1
            per_page = 1000

            while True:
                try:
                    response = await client.get(
                        config["url"],
                        params={
                            "serviceKey": api_key,
                            "page": page,
                            "perPage": per_page
                        }
                    )

                    if response.status_code != 200:
                        print(f"  오류: HTTP {response.status_code}")
                        print(f"  응답: {response.text[:200]}")
                        break

                    result = response.json()
                    data = result.get("data", [])

                    if not data:
                        break

                    all_data.extend(data)
                    print(f"  페이지 {page}: {len(data)}건 (누적 {len(all_data)}건)")

                    # 다음 페이지 확인
                    total_count = result.get("totalCount", 0)
                    if len(all_data) >= total_count:
                        break

                    page += 1

                except Exception as e:
                    print(f"  오류: {e}")
                    break

            # 저장
            output_path = OUTPUT_DIR / config["output"]
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(all_data, f, ensure_ascii=False, indent=2)

            print(f"  저장 완료: {output_path} ({len(all_data)}건)")


def main():
    api_key = os.environ.get("PUBLIC_DATA_API_KEY")

    if not api_key:
        print("=" * 60)
        print("공공데이터 API 키가 필요합니다.")
        print()
        print("설정 방법:")
        print("1. https://www.data.go.kr 에서 회원가입")
        print("2. 다음 데이터셋에서 '활용신청' 클릭:")
        print("   - 서울교통공사 1-8호선 역사 좌표(위경도) 정보")
        print("   - 서울특별시_역간 거리 및 소요시간 정보")
        print("   - 서울교통공사_환승역거리 소요시간 정보")
        print("3. API 키 발급 후 환경변수 설정:")
        print("   export PUBLIC_DATA_API_KEY=your_api_key")
        print()
        print("또는 CSV 파일을 직접 다운로드하여 raw/ 폴더에 저장하세요.")
        print("=" * 60)
        return

    print("서울 지하철 공공데이터 다운로드를 시작합니다...")
    asyncio.run(download_data(api_key))
    print("\n다운로드 완료!")
    print(f"다음 단계: python scripts/subway/build_graph.py")


if __name__ == "__main__":
    main()
