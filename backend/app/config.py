"""환경 설정 모듈"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # GCP
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None

    # Gemini API
    GEMINI_API_KEY: str = ""

    # Google Maps API
    GOOGLE_MAPS_API_KEY: str = ""

    # App
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # CORS (Vite 개발 서버가 포트 충돌 시 자동으로 다음 포트 사용)
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:5176,http://localhost:5177,http://localhost:5178,http://localhost:5179,http://localhost:5180,http://localhost:3000"

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
