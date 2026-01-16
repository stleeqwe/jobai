"""
서울 지하철 기반 통근시간 계산 모듈 (Backend 버전)

shared 모듈을 상속하여 Backend 특화 설정 적용:
- BASE_COMMUTE_MINUTES = 10 (최소 통근시간)
- 정확한 분 단위 포맷팅 ("{minutes}분")
"""

import sys
from pathlib import Path
from typing import Tuple

# shared 패키지 경로 추가
_shared_path = Path(__file__).parent.parent.parent.parent / "shared"
if str(_shared_path) not in sys.path:
    sys.path.insert(0, str(_shared_path))

from seoul_subway_commute import SeoulSubwayCommute as BaseSeoulSubwayCommute


class SeoulSubwayCommute(BaseSeoulSubwayCommute):
    """Backend용 지하철 통근시간 계산기

    특징:
    - 최소 통근시간 10분 적용 (동일 구/인접 지역)
    - 정확한 분 단위 포맷팅 (반올림 없음)
    """

    # 최소 통근시간 (분)
    BASE_COMMUTE_MINUTES = 10

    def format_time(self, minutes: int) -> Tuple[int, str]:
        """정확한 분 단위 포맷팅 (Backend 특화)"""
        return minutes, f"{minutes}분"

    # 하위 호환성을 위한 별칭
    _format_commute_time = format_time


# 모듈 레벨 export
__all__ = ["SeoulSubwayCommute"]
