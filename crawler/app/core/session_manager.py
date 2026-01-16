"""세션 관리 모듈 - httpx 기반 쿠키/세션 관리"""

import random
from typing import Optional
import httpx

from app.config import CrawlerConfig, USER_AGENTS, settings
from app.logging_config import get_logger

logger = get_logger("crawler.session")


class SessionManager:
    """httpx 기반 세션 관리"""

    # 프록시 설정 (IPRoyal)
    PROXY_HOST = settings.PROXY_HOST
    PROXY_PORT = settings.PROXY_PORT
    PROXY_USERNAME = settings.PROXY_USERNAME
    PROXY_PASSWORD = settings.PROXY_PASSWORD

    def __init__(self, use_proxy: bool = False):
        self.use_proxy = use_proxy
        self.client: Optional[httpx.AsyncClient] = None
        self.cookies: Optional[httpx.Cookies] = None
        self._warned_proxy_config = False

    def _proxy_configured(self) -> bool:
        return all([
            self.PROXY_HOST,
            self.PROXY_PORT,
            self.PROXY_USERNAME,
            self.PROXY_PASSWORD,
        ])

    def _get_proxy_url(self, worker_id: Optional[int] = None, lifetime: str = "10m") -> Optional[str]:
        """프록시 URL 생성

        Args:
            worker_id: 워커 ID (None이면 랜덤 IP, 있으면 Sticky 세션)
            lifetime: Sticky 세션 유지 시간 (기본 10분)

        Returns:
            프록시 URL 또는 None
        """
        if not self.use_proxy:
            return None
        if not self._proxy_configured():
            if not self._warned_proxy_config:
                logger.warning("프록시 설정 누락: PROXY_* 환경변수 확인 필요")
                self._warned_proxy_config = True
            return None

        if worker_id is not None:
            # Sticky 세션: 워커별 고정 IP
            session_id = f"worker{worker_id:02d}"
            return (
                f"http://{self.PROXY_USERNAME}:{self.PROXY_PASSWORD}"
                f"_session-{session_id}_lifetime-{lifetime}"
                f"@{self.PROXY_HOST}:{self.PROXY_PORT}"
            )
        else:
            # Random 세션: 매 요청 새 IP
            return f"http://{self.PROXY_USERNAME}:{self.PROXY_PASSWORD}@{self.PROXY_HOST}:{self.PROXY_PORT}"

    async def initialize(self) -> httpx.AsyncClient:
        """세션 초기화 및 쿠키 획득"""
        proxy_url = self._get_proxy_url()

        self.client = httpx.AsyncClient(
            timeout=CrawlerConfig.DEFAULT_TIMEOUT,
            headers={
                "User-Agent": random.choice(USER_AGENTS),
                **CrawlerConfig.DEFAULT_HEADERS,
            },
            follow_redirects=True,
            proxy=proxy_url,
        )

        # 세션 쿠키 획득
        resp = await self.client.get(
            CrawlerConfig.get_joblist_url(),
            params={"menucode": "local", "local": CrawlerConfig.SEOUL_LOCAL_CODE}
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


    def create_worker_client(
        self,
        worker_id: int,
        cookies: Optional[httpx.Cookies] = None,
        lifetime: str = "10m"
    ) -> httpx.AsyncClient:
        """워커별 Sticky 세션 클라이언트 생성

        Args:
            worker_id: 워커 ID (0-9 등)
            cookies: 공유 쿠키 (None이면 새로 획득 필요)
            lifetime: 세션 유지 시간

        Returns:
            워커 전용 AsyncClient
        """
        proxy_url = self._get_proxy_url(worker_id=worker_id, lifetime=lifetime)

        return httpx.AsyncClient(
            timeout=CrawlerConfig.DEFAULT_TIMEOUT,
            headers={
                "User-Agent": USER_AGENTS[worker_id % len(USER_AGENTS)],
                **CrawlerConfig.DEFAULT_HEADERS,
            },
            follow_redirects=True,
            proxy=proxy_url,
            cookies=cookies,
        )


class ProxySessionManager(SessionManager):
    """프록시 전용 세션 관리자 (폴백용)"""

    def __init__(self):
        super().__init__(use_proxy=True)

    async def switch_to_proxy(self, existing_cookies: httpx.Cookies) -> httpx.AsyncClient:
        """기존 쿠키를 유지하면서 프록시 클라이언트로 전환"""
        proxy_url = self._get_proxy_url()

        self.client = httpx.AsyncClient(
            timeout=CrawlerConfig.DEFAULT_TIMEOUT,
            headers={
                "User-Agent": random.choice(USER_AGENTS),
                **CrawlerConfig.DEFAULT_HEADERS,
            },
            follow_redirects=True,
            proxy=proxy_url,
            cookies=existing_cookies,  # 기존 쿠키 유지
        )

        self.cookies = self.client.cookies
        logger.info("프록시 세션으로 전환 완료")

        return self.client
