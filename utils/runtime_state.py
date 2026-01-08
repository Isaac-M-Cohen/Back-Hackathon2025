"""Shared runtime state for client-side settings."""

from __future__ import annotations


_CLIENT_OS: str | None = None


def set_client_os(value: str | None) -> None:
    if value is None:
        return
    normalized = _normalize_client_os(value)
    if normalized:
        global _CLIENT_OS
        _CLIENT_OS = normalized


def get_client_os() -> str | None:
    return _CLIENT_OS


def _normalize_client_os(value: str) -> str | None:
    text = str(value).strip()
    if not text:
        return None
    lower = text.lower()
    if lower in {"darwin", "mac", "macos", "mac os", "mac os x", "osx"}:
        return "Darwin"
    if lower in {"windows", "win32", "win"}:
        return "Windows"
    if lower in {"linux", "gnu/linux"}:
        return "Linux"
    return text
