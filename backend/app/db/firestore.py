"""Firestore 클라이언트 모듈"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any

from app.config import settings

logger = logging.getLogger(__name__)

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


# ========== 대화 히스토리 관련 함수 ==========

async def save_conversation_history(
    conversation_id: str,
    history: List[Any],
    search_cache: Optional[Dict[str, Any]] = None
) -> bool:
    """
    대화 히스토리를 Firestore에 저장

    Args:
        conversation_id: 대화 ID
        history: Gemini 대화 히스토리 (직렬화 가능한 형태)
        search_cache: 검색 결과 캐시 (선택)

    Returns:
        저장 성공 여부
    """
    db = get_db()
    if db is None:
        logger.warning("Firestore 미연결 - 대화 히스토리 저장 건너뜀")
        return False

    try:
        # 히스토리를 직렬화 가능한 형태로 변환
        serialized_history = _serialize_history(history)

        doc_data = {
            "conversation_id": conversation_id,
            "history": serialized_history,
            "updated_at": datetime.now(),
        }

        # 검색 캐시가 있으면 함께 저장
        if search_cache:
            # jobs는 너무 크므로 ID만 저장
            doc_data["search_cache"] = {
                "job_ids": [j.get("id") for j in search_cache.get("jobs", [])],
                "search_params": search_cache.get("search_params", {}),
            }

        await db.collection("conversations").document(conversation_id).set(
            doc_data, merge=True
        )
        return True

    except Exception as e:
        logger.error(f"대화 히스토리 저장 실패: {e}")
        return False


async def load_conversation_history(
    conversation_id: str
) -> Optional[Dict[str, Any]]:
    """
    Firestore에서 대화 히스토리 로드

    Args:
        conversation_id: 대화 ID

    Returns:
        대화 데이터 또는 None
    """
    db = get_db()
    if db is None:
        return None

    try:
        doc = await db.collection("conversations").document(conversation_id).get()
        if doc.exists:
            data = doc.to_dict()
            return {
                "history": _deserialize_history(data.get("history", [])),
                "search_cache": data.get("search_cache"),
                "updated_at": data.get("updated_at"),
            }
        return None

    except Exception as e:
        logger.error(f"대화 히스토리 로드 실패: {e}")
        return None


def _serialize_history(history: List[Any]) -> List[Dict]:
    """Gemini 히스토리를 JSON 직렬화 가능한 형태로 변환"""
    serialized = []
    for item in history:
        try:
            if hasattr(item, "parts"):
                # Gemini Content 객체
                parts_data = []
                for part in item.parts:
                    if hasattr(part, "text") and part.text:
                        parts_data.append({"type": "text", "content": part.text})
                    elif hasattr(part, "function_call") and part.function_call:
                        parts_data.append({
                            "type": "function_call",
                            "name": part.function_call.name,
                            "args": dict(part.function_call.args) if part.function_call.args else {}
                        })
                    elif hasattr(part, "function_response") and part.function_response:
                        parts_data.append({
                            "type": "function_response",
                            "name": part.function_response.name,
                            "response": dict(part.function_response.response) if part.function_response.response else {}
                        })

                serialized.append({
                    "role": item.role if hasattr(item, "role") else "unknown",
                    "parts": parts_data
                })
            elif isinstance(item, dict):
                serialized.append(item)
        except Exception as e:
            logger.warning(f"히스토리 항목 직렬화 실패: {e}")
            continue

    return serialized


def _deserialize_history(serialized: List[Dict]) -> List[Dict]:
    """직렬화된 히스토리를 반환 (Gemini에서 재구성)"""
    # 현재는 그대로 반환 (Gemini 재구성은 gemini.py에서 처리)
    return serialized
