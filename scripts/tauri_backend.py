"""Launch the FastAPI backend for Tauri as a local-only server."""

from __future__ import annotations

import os

import uvicorn

from utils.settings_store import get_settings


def main() -> None:
    host = os.getenv("EASY_API_HOST", "127.0.0.1")
    port = int(os.getenv("EASY_API_PORT", "8000"))
    settings = get_settings()
    access_log = bool(settings.get("http_access_log", False))
    log_level = str(settings.get("log_level", "INFO")).upper()
    if log_level == "DEEP":
        log_level = "DEBUG"
    uvicorn.run(
        "api.server:app",
        host=host,
        port=port,
        log_level=log_level.lower(),
        access_log=access_log,
    )


if __name__ == "__main__":
    main()
