"""환경 설정 모듈"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # GCP
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None

    # Gemini API
    GEMINI_API_KEY: str = ""

    # App
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Gemini
    GEMINI_MODEL: str = "gemini-2.0-flash-lite"

    # Search
    DEFAULT_SEARCH_LIMIT: int = 10
    MAX_SEARCH_LIMIT: int = 50

    @property
    def allowed_origins_list(self) -> list[str]:
        """CORS 허용 오리진 리스트"""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
