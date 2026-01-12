from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # GCP
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None

    # Crawler Settings
    CRAWL_DELAY_SECONDS: float = 1.0
    MAX_PAGES: int = 100
    BATCH_SIZE: int = 100

    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
