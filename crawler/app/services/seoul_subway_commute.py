"""
서울 지하철 기반 통근시간 계산 모듈 (Crawler 버전)

shared 모듈을 그대로 사용:
- 10분 단위 반올림 포맷팅 ("약 N분")
- 공간 인덱싱 활성화 (GRID_SIZE = 0.01)
"""

import sys
from pathlib import Path

# shared 패키지 경로 추가
_shared_path = Path(__file__).parent.parent.parent.parent / "shared"
if str(_shared_path) not in sys.path:
    sys.path.insert(0, str(_shared_path))

# shared 모듈에서 직접 import (기본 설정 그대로 사용)
from seoul_subway_commute import SeoulSubwayCommute

# 모듈 레벨 export
__all__ = ["SeoulSubwayCommute"]
