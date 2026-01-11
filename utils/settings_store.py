"""In-memory cache for app settings."""

from __future__ import annotations

import threading
from typing import Any

from utils.file_utils import load_json

_lock = threading.Lock()
_settings_cache: dict[str, Any] = {}


def refresh_settings() -> dict[str, Any]:
    """Reload settings from disk and replace the cache."""
    data = load_json("config/app_settings.json")
    if not isinstance(data, dict):
        data = {}
    with _lock:
        _settings_cache.clear()
        _settings_cache.update(data)
        return dict(_settings_cache)


def get_settings() -> dict[str, Any]:
    """Return a copy of the cached settings."""
    with _lock:
        if not _settings_cache:
            refresh_settings()
        return dict(_settings_cache)


def is_deep_logging() -> bool:
    """Return True when log_level requests deep tracing."""
    level = str(get_settings().get("log_level", "")).upper()
    return level in {"DEEP"}
