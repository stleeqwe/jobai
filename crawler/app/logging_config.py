"""크롤러 로깅 설정 모듈"""

import logging
import sys
import time
import functools
from datetime import datetime
from typing import Optional, Any, Dict
from contextlib import contextmanager

from app.config import settings


# 로거 이름 상수
LOGGER_NAME = "crawler"


def setup_logger(
    name: str = LOGGER_NAME,
    level: Optional[int] = None,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    크롤러 로거 설정

    Args:
        name: 로거 이름
        level: 로그 레벨 (None이면 settings.LOG_LEVEL 사용)
        log_file: 파일 출력 경로 (None이면 settings.LOG_FILE 사용)

    Returns:
        설정된 로거
    """
    logger = logging.getLogger(name)

    # 이미 핸들러가 설정되어 있으면 스킵
    if logger.handlers:
        return logger

    # 로그 레벨 결정 (환경변수 우선)
    if level is None:
        level_name = getattr(settings, "LOG_LEVEL", "DEBUG").upper()
        level = getattr(logging, level_name, logging.DEBUG)
    logger.setLevel(level)

    # 파일 경로 결정 (환경변수 우선)
    if log_file is None:
        log_file = getattr(settings, "LOG_FILE", None)

    # 포맷터 설정
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 파일 핸들러 (옵션)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # 상위 로거로 전파 방지
    logger.propagate = False

    return logger


def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    """로거 인스턴스 반환"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger


# ========== 데코레이터 ==========

def log_function(logger: Optional[logging.Logger] = None):
    """
    함수 진입/종료 + 소요시간 로깅 데코레이터

    Usage:
        @log_function()
        async def my_function():
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            _logger = logger or get_logger()
            func_name = func.__name__

            # 주요 인자 추출 (너무 길면 생략)
            args_preview = _format_args_preview(args, kwargs)

            _logger.debug(f"[ENTER] {func_name}({args_preview})")
            start_time = time.perf_counter()

            try:
                result = await func(*args, **kwargs)
                elapsed = time.perf_counter() - start_time

                # 결과 요약
                result_preview = _format_result_preview(result)
                _logger.debug(f"[EXIT] {func_name} -> {result_preview} ({elapsed:.2f}s)")

                return result
            except Exception as e:
                elapsed = time.perf_counter() - start_time
                _logger.error(f"[ERROR] {func_name} failed: {e} ({elapsed:.2f}s)")
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            _logger = logger or get_logger()
            func_name = func.__name__

            args_preview = _format_args_preview(args, kwargs)
            _logger.debug(f"[ENTER] {func_name}({args_preview})")
            start_time = time.perf_counter()

            try:
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - start_time

                result_preview = _format_result_preview(result)
                _logger.debug(f"[EXIT] {func_name} -> {result_preview} ({elapsed:.2f}s)")

                return result
            except Exception as e:
                elapsed = time.perf_counter() - start_time
                _logger.error(f"[ERROR] {func_name} failed: {e} ({elapsed:.2f}s)")
                raise

        # async/sync 함수 구분
        if asyncio_iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


@contextmanager
def log_timing(operation: str, logger: Optional[logging.Logger] = None):
    """
    컨텍스트 매니저로 구간 소요시간 측정

    Usage:
        with log_timing("페이지 파싱"):
            soup = BeautifulSoup(html, "lxml")
    """
    _logger = logger or get_logger()
    start_time = time.perf_counter()
    _logger.debug(f"[START] {operation}")

    try:
        yield
    finally:
        elapsed = time.perf_counter() - start_time
        _logger.debug(f"[END] {operation} ({elapsed:.2f}s)")


# ========== HTTP 로깅 ==========

def log_http_request(
    logger: logging.Logger,
    method: str,
    url: str,
    params: Optional[Dict] = None,
    attempt: int = 1,
):
    """HTTP 요청 로깅"""
    params_str = f" params={params}" if params else ""
    logger.debug(f"[HTTP] {method} {url}{params_str} (attempt {attempt})")


def log_http_response(
    logger: logging.Logger,
    url: str,
    status_code: int,
    content_length: int,
    elapsed_ms: float,
):
    """HTTP 응답 로깅"""
    level = logging.DEBUG if status_code == 200 else logging.WARNING
    logger.log(level, f"[HTTP] <- {status_code} {url} ({content_length} bytes, {elapsed_ms:.0f}ms)")


def log_http_error(
    logger: logging.Logger,
    url: str,
    error: Exception,
    attempt: int,
    max_retries: int,
):
    """HTTP 에러 로깅"""
    logger.warning(f"[HTTP] ERROR {url}: {error} (attempt {attempt}/{max_retries})")


# ========== 파싱 로깅 ==========

def log_parse_result(
    logger: logging.Logger,
    job_id: str,
    fields: Dict[str, Any],
    sample_fields: Optional[list] = None,
):
    """
    파싱 결과 샘플 로깅

    Args:
        logger: 로거
        job_id: 공고 ID
        fields: 파싱된 필드 딕셔너리
        sample_fields: 출력할 필드 목록 (None이면 기본값)
    """
    if sample_fields is None:
        sample_fields = ["title", "company_name", "salary_text", "job_type", "location_full"]

    sample = {k: _truncate(fields.get(k, ""), 50) for k in sample_fields if k in fields}
    logger.debug(f"[PARSE] {job_id}: {sample}")


def log_parse_summary(
    logger: logging.Logger,
    page: int,
    total_items: int,
    parsed_count: int,
    failed_count: int,
):
    """페이지 파싱 요약 로깅"""
    success_rate = (parsed_count / total_items * 100) if total_items > 0 else 0
    logger.info(
        f"[PARSE] 페이지 {page}: {total_items}개 중 {parsed_count}개 성공 "
        f"({success_rate:.1f}%), 실패 {failed_count}개"
    )


# ========== 유틸리티 ==========

def _format_args_preview(args: tuple, kwargs: dict, max_len: int = 100) -> str:
    """인자 미리보기 포맷팅"""
    parts = []

    # self 제외한 위치 인자
    for i, arg in enumerate(args):
        if i == 0 and hasattr(arg, '__class__'):
            continue  # self 스킵
        parts.append(_truncate(repr(arg), 30))

    # 키워드 인자
    for k, v in kwargs.items():
        parts.append(f"{k}={_truncate(repr(v), 30)}")

    result = ", ".join(parts)
    return _truncate(result, max_len)


def _format_result_preview(result: Any, max_len: int = 100) -> str:
    """결과 미리보기 포맷팅"""
    if result is None:
        return "None"
    if isinstance(result, (list, tuple)):
        return f"[{len(result)} items]"
    if isinstance(result, dict):
        return f"{{{len(result)} keys}}"
    if isinstance(result, set):
        return f"set({len(result)} items)"
    return _truncate(repr(result), max_len)


def _truncate(text: Any, max_len: int) -> str:
    """텍스트 길이 제한"""
    text = str(text)
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def asyncio_iscoroutinefunction(func) -> bool:
    """async 함수 여부 확인"""
    import asyncio
    return asyncio.iscoroutinefunction(func)
