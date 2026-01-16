from pydantic_settings import BaseSettings
from typing import List, Optional, Dict


class Settings(BaseSettings):
    # GCP
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None

    # Crawler Settings
    CRAWL_DELAY_SECONDS: float = 1.0
    MAX_PAGES: int = 100
    BATCH_SIZE: int = 100

    # Proxy Settings (IPRoyal)
    PROXY_HOST: str = ""
    PROXY_PORT: int = 0
    PROXY_USERNAME: str = ""
    PROXY_PASSWORD: str = ""

    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Logging
    LOG_LEVEL: str = "DEBUG"  # DEBUG, INFO, WARNING, ERROR
    LOG_FILE: Optional[str] = None  # 파일 로깅 경로 (None이면 콘솔만)

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()


# ========== 크롤러 상수 (중앙화) ==========

class CrawlerConfig:
    """크롤러 관련 상수 중앙 관리"""

    # URLs
    BASE_URL = "https://www.jobkorea.co.kr"
    AJAX_ENDPOINT = "/Recruit/Home/_GI_List"
    DETAIL_PATH = "/Recruit/GI_Read"
    JOBLIST_PATH = "/recruit/joblist"

    # Timeouts (초)
    DEFAULT_TIMEOUT = 30.0
    DETAIL_TIMEOUT = 15.0

    # HTTP Headers
    DEFAULT_HEADERS: Dict[str, str] = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    # Pagination
    JOBS_PER_PAGE = 40
    MAX_PAGES = 250

    # Rate Limiting
    INITIAL_DELAY = 0.05  # 50ms
    MIN_DELAY = 0.05
    MAX_DELAY = 5.0

    # 지역 코드
    SEOUL_LOCAL_CODE = "I000"

    @classmethod
    def get_detail_url(cls, job_id: str) -> str:
        return f"{cls.BASE_URL}{cls.DETAIL_PATH}/{job_id}"

    @classmethod
    def get_ajax_url(cls) -> str:
        return f"{cls.BASE_URL}{cls.AJAX_ENDPOINT}"

    @classmethod
    def get_joblist_url(cls) -> str:
        return f"{cls.BASE_URL}{cls.JOBLIST_PATH}"


# User-Agent 로테이션 풀
USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]
