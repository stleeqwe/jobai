"""세션 관리 모듈 - httpx 기반 쿠키/세션 관리"""

import random
from typing import Optional
import httpx

from app.config import USER_AGENTS
from app.logging_config import get_logger

logger = get_logger("crawler.session")


class SessionManager:
    """httpx 기반 세션 관리"""

    BASE_URL = "https://www.jobkorea.co.kr"
    JOBLIST_URL = f"{BASE_URL}/recruit/joblist"

    # 프록시 설정 (IPRoyal)
    PROXY_HOST = "geo.iproyal.com"
    PROXY_PORT = 12321
    PROXY_USERNAME = "wjmD9FjEss6TCmTC"
    PROXY_PASSWORD = "PFZsSKOcUmfIb0Kj"

    def __init__(self, use_proxy: bool = False):
        self.use_proxy = use_proxy
        self.client: Optional[httpx.AsyncClient] = None
        self.cookies: Optional[httpx.Cookies] = None

    def _get_proxy_url(self) -> Optional[str]:
        """프록시 URL 생성"""
        if not self.use_proxy:
            return None
        return f"http://{self.PROXY_USERNAME}:{self.PROXY_PASSWORD}@{self.PROXY_HOST}:{self.PROXY_PORT}"

    async def initialize(self) -> httpx.AsyncClient:
        """세션 초기화 및 쿠키 획득"""
        proxy_url = self._get_proxy_url()

        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9",
            },
            follow_redirects=True,
            proxy=proxy_url,
        )

        # 세션 쿠키 획득
        resp = await self.client.get(
            self.JOBLIST_URL,
            params={"menucode": "local", "local": "I000"}
        )

        self.cookies = self.client.cookies

        logger.info(f"세션 획득 완료: {list(self.cookies.keys())}")
        logger.info(f"프록시: {'ON' if self.use_proxy else 'OFF'}")

        return self.client

    def get_cookies(self) -> httpx.Cookies:
        """현재 세션 쿠키 반환"""
        if not self.cookies:
            raise RuntimeError("세션이 초기화되지 않음. initialize() 먼저 호출하세요.")
        return self.cookies

    async def close(self):
        """클라이언트 종료"""
        if self.client:
            await self.client.aclose()
            self.client = None
            self.cookies = None


class ProxySessionManager(SessionManager):
    """프록시 전용 세션 관리자 (폴백용)"""

    def __init__(self):
        super().__init__(use_proxy=True)

    async def switch_to_proxy(self, existing_cookies: httpx.Cookies) -> httpx.AsyncClient:
        """기존 쿠키를 유지하면서 프록시 클라이언트로 전환"""
        proxy_url = self._get_proxy_url()

        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9",
            },
            follow_redirects=True,
            proxy=proxy_url,
            cookies=existing_cookies,  # 기존 쿠키 유지
        )

        self.cookies = self.client.cookies
        logger.info("프록시 세션으로 전환 완료")

        return self.client
