import os
from typing import Optional, Tuple

_PROXY_SETTINGS: Optional[Tuple[str, int, str, str]] = None


def _load_proxy_settings() -> Tuple[str, int, str, str]:
    host = os.getenv("PROXY_HOST", "").strip()
    port_raw = os.getenv("PROXY_PORT", "").strip()
    username = os.getenv("PROXY_USERNAME", "").strip()
    password = os.getenv("PROXY_PASSWORD", "").strip()

    missing = [
        key
        for key, value in (
            ("PROXY_HOST", host),
            ("PROXY_PORT", port_raw),
            ("PROXY_USERNAME", username),
            ("PROXY_PASSWORD", password),
        )
        if not value
    ]
    if missing:
        raise SystemExit(f"Missing proxy env: {', '.join(missing)}")

    try:
        port = int(port_raw)
    except ValueError as exc:
        raise SystemExit(f"Invalid PROXY_PORT: {port_raw}") from exc

    if port <= 0:
        raise SystemExit(f"Invalid PROXY_PORT: {port_raw}")

    return host, port, username, password


def _get_proxy_settings() -> Tuple[str, int, str, str]:
    global _PROXY_SETTINGS
    if _PROXY_SETTINGS is None:
        _PROXY_SETTINGS = _load_proxy_settings()
    return _PROXY_SETTINGS


def get_proxy_url(session_id: Optional[str] = None, lifetime: str = "10m") -> str:
    host, port, username, password = _get_proxy_settings()

    if session_id:
        password = f"{password}_session-{session_id}_lifetime-{lifetime}"

    return f"http://{username}:{password}@{host}:{port}"
