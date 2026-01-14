"""FastAPI 메인 애플리케이션 - V6"""

import smtplib
from email.mime.text import MIMEText
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.routers import chat_router
from app.db import init_firestore, check_connection
from app.services.gemini import check_gemini
from app.services.job_search import get_job_stats
from app.services.subway import check_subway_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행"""
    # 시작 시
    print(f"[JobChat API V6] 환경: {settings.ENVIRONMENT}")
    print(f"[JobChat API V6] 프로젝트: {settings.GOOGLE_CLOUD_PROJECT}")
    init_firestore()
    yield
    # 종료 시
    print("[JobChat API V6] 종료")


app = FastAPI(
    title="JobChat API",
    description="자연어 기반 채용공고 검색 서비스 API - V6 Simple Agentic",
    version="6.0.0",
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

    서비스 상태 및 외부 연결 확인 (V6: Subway 서비스)
    """
    return {
        "status": "healthy",
        "version": "6.0.0",
        "environment": settings.ENVIRONMENT,
        "services": {
            "firestore": "connected" if check_connection() else "disconnected",
            "gemini": "available" if check_gemini() else "unavailable",
            "subway": "available" if check_subway_service() else "unavailable"
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
        "version": "6.0.0",
        "architecture": "Simple Agentic",
        "docs": "/docs"
    }


@app.get("/geocode/reverse")
async def reverse_geocode_endpoint(lat: float, lng: float):
    """
    역지오코딩 - 좌표를 구/동 주소로 변환

    Google Maps Geocoding API를 사용하여 좌표를 한국어 주소로 변환합니다.

    Args:
        lat: 위도
        lng: 경도

    Returns:
        {
            "address": "강남구 역삼동",
            "latitude": lat,
            "longitude": lng,
            "gu": "강남구",
            "dong": "역삼동"
        }
    """
    from app.services.geocoding import reverse_geocode

    try:
        result = await reverse_geocode(lat, lng)
        if result:
            return {
                "address": result["address"],
                "latitude": lat,
                "longitude": lng,
                "gu": result.get("gu"),
                "dong": result.get("dong")
            }
    except Exception as e:
        return {"address": None, "latitude": lat, "longitude": lng, "error": str(e)}

    return {"address": None, "latitude": lat, "longitude": lng}


class FeedbackRequest(BaseModel):
    message: str


@app.post("/feedback")
async def send_feedback(request: FeedbackRequest):
    """사용자 피드백 이메일 전송"""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="메시지를 입력해주세요")

    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        raise HTTPException(status_code=500, detail="이메일 설정이 되어있지 않습니다")

    try:
        msg = MIMEText(request.message, "plain", "utf-8")
        msg["Subject"] = "[JOBBOT 피드백]"
        msg["From"] = settings.GMAIL_USER
        msg["To"] = settings.GMAIL_USER

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
            server.send_message(msg)

        return {"success": True, "message": "피드백이 전송되었습니다"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"전송 실패: {str(e)}")
