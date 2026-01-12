"""Firestore 클라이언트 모듈"""

from typing import Optional

from app.config import settings

# Firestore 클라이언트 (lazy initialization)
_db = None
_initialized = False


def init_firestore() -> None:
    """Firestore 클라이언트 초기화"""
    global _db, _initialized
    if _initialized:
        return

    _initialized = True

    try:
        from google.cloud import firestore
        from google.oauth2 import service_account

        # 서비스 계정 credentials 명시적 로드
        credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
        if credentials_path:
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path
            )
            _db = firestore.AsyncClient(
                project=settings.GOOGLE_CLOUD_PROJECT,
                credentials=credentials
            )
        else:
            # ADC 사용
            _db = firestore.AsyncClient(project=settings.GOOGLE_CLOUD_PROJECT)

        print("[Firestore] 연결 성공")
    except Exception as e:
        print(f"[Firestore] 연결 실패 (로컬 모드): {e}")
        _db = None


def get_db():
    """Firestore 클라이언트 반환"""
    global _db
    if not _initialized:
        init_firestore()
    return _db


def check_connection() -> bool:
    """Firestore 연결 상태 확인"""
    return _db is not None
