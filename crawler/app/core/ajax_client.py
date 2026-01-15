"""AJAX 엔드포인트 클라이언트 - 목록 페이지 수집"""

import re
from typing import List, Optional, Set
import httpx

from app.logging_config import get_logger

logger = get_logger("crawler.ajax")


class AjaxClient:
    """AJAX 엔드포인트 클라이언트"""

    BASE_URL = "https://www.jobkorea.co.kr"
    AJAX_ENDPOINT = "/Recruit/Home/_GI_List"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def fetch_page(
        self,
        page_num: int,
        local: str = "I000"
    ) -> List[str]:
        """
        목록 페이지 AJAX 호출

        Args:
            page_num: 페이지 번호 (1부터 시작)
            local: 지역 코드 (I000 = 서울)

        Returns:
            List[str]: 추출된 Job ID 목록
        """
        try:
            resp = await self.client.get(
                f"{self.BASE_URL}{self.AJAX_ENDPOINT}",
                params={"Page": page_num, "local": local},
                headers={"X-Requested-With": "XMLHttpRequest"}
            )

            if resp.status_code != 200:
                logger.warning(f"AJAX 호출 실패: 페이지 {page_num}, 상태 {resp.status_code}")
                return []

            # GI_Read/숫자 패턴으로 ID 추출
            matches = re.findall(r'GI_Read/(\d+)', resp.text)
            unique_ids = list(set(matches))

            logger.debug(f"페이지 {page_num}: {len(unique_ids)}개 ID 추출")
            return unique_ids

        except Exception as e:
            logger.error(f"AJAX 호출 예외: 페이지 {page_num}, {e}")
            return []

    async def get_total_count(self, local: str = "I000") -> int:
        """전체 공고 수 조회"""
        try:
            resp = await self.client.get(
                f"{self.BASE_URL}{self.AJAX_ENDPOINT}",
                params={"Page": 1, "local": local},
                headers={"X-Requested-With": "XMLHttpRequest"}
            )

            if resp.status_code != 200:
                return 0

            # hdnGICnt 값 추출
            match = re.search(r'hdnGICnt.*?value="([\d,]+)"', resp.text)
            if match:
                return int(match.group(1).replace(",", ""))

            return 0

        except Exception as e:
            logger.error(f"전체 공고 수 조회 실패: {e}")
            return 0

    async def fetch_pages_batch(
        self,
        start_page: int,
        end_page: int,
        local: str = "I000"
    ) -> Set[str]:
        """
        여러 페이지 순차 호출

        Args:
            start_page: 시작 페이지
            end_page: 종료 페이지 (포함)
            local: 지역 코드

        Returns:
            Set[str]: 고유 Job ID 세트
        """
        all_ids: Set[str] = set()

        for page in range(start_page, end_page + 1):
            ids = await self.fetch_page(page, local)
            all_ids.update(ids)

        return all_ids


class BlockedError(Exception):
    """차단 감지 예외"""
    pass


class AdaptiveRateLimiter:
    """적응형 속도 제한"""

    def __init__(self, initial_delay: float = 0.05):
        self.delay = initial_delay  # 초기 50ms
        self.min_delay = 0.05  # 최소 50ms
        self.max_delay = 5.0  # 최대 5초
        self.consecutive_errors = 0
        self.blocked = False

    def on_success(self):
        """요청 성공 시"""
        self.consecutive_errors = 0
        # 점진적으로 속도 증가 (최소 유지)
        self.delay = max(self.min_delay, self.delay * 0.95)

    def on_error(self, status_code: int):
        """요청 실패 시"""
        self.consecutive_errors += 1

        if status_code in [403, 429]:
            # 차단 감지: 속도 대폭 감소
            self.delay = min(self.max_delay, self.delay * 3)

            if self.consecutive_errors >= 5:
                self.blocked = True

    def is_blocked(self) -> bool:
        return self.blocked

    def get_delay(self) -> float:
        return self.delay

    def reset(self):
        """상태 리셋"""
        self.delay = self.min_delay
        self.consecutive_errors = 0
        self.blocked = False
