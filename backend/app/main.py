"""FastAPI 메인 애플리케이션"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import chat_router
from app.db import init_firestore, check_connection
from app.services.gemini import check_gemini
from app.services.job_search import get_job_stats


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행"""
    # 시작 시
    print(f"[JobChat API] 환경: {settings.ENVIRONMENT}")
    print(f"[JobChat API] 프로젝트: {settings.GOOGLE_CLOUD_PROJECT}")
    init_firestore()
    yield
    # 종료 시
    print("[JobChat API] 종료")


app = FastAPI(
    title="JobChat API",
    description="자연어 기반 채용공고 검색 서비스 API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(chat_router, tags=["chat"])


@app.get("/health")
async def health_check():
    """
    헬스체크 엔드포인트

    서비스 상태 및 외부 연결 확인
    """
    return {
        "status": "healthy",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "services": {
            "firestore": "connected" if check_connection() else "disconnected",
            "gemini": "available" if check_gemini() else "unavailable"
        }
    }


@app.get("/stats")
async def stats():
    """
    서비스 통계 조회

    - 전체 공고 수
    - 활성 공고 수
    - 마지막 크롤링 시간
    """
    try:
        return await get_job_stats()
    except Exception as e:
        return {
            "error": str(e),
            "total_jobs": 0,
            "active_jobs": 0,
            "last_crawl": None
        }


@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "service": "JobChat API",
        "version": "1.0.0",
        "docs": "/docs"
    }
