"""Timestamped logging helpers."""

from __future__ import annotations

import builtins
import time
from typing import Any


_LEVELS = {"DEEP", "DEBUG", "INFO", "WARN", "ERROR"}


def _split_tags(message: str) -> tuple[list[str], str]:
    tags: list[str] = []
    remaining = message.lstrip()
    while remaining.startswith("["):
        end = remaining.find("]")
        if end == -1:
            break
        tag = remaining[1:end].strip()
        if not tag:
            break
        tags.append(tag)
        remaining = remaining[end + 1 :].lstrip()
    return tags, remaining


def _format_message(message: str) -> str:
    tags, remaining = _split_tags(message)
    system = "APP"
    variant = None
    extra_tags: list[str] = []
    if tags:
        first = tags[0].upper()
        if first in _LEVELS:
            variant = tags[0].upper()
            system = tags[1] if len(tags) > 1 else "APP"
            extra_tags = tags[2:]
        else:
            system = tags[0]
            variant = tags[1] if len(tags) > 1 else None
            extra_tags = tags[2:]
    extra = f" [{' '.join(extra_tags)}]" if extra_tags else ""
    suffix = f" {remaining}" if remaining else ""
    if variant:
        return f"[{system}][{variant}]{extra}{suffix}"
    return f"[{system}]{extra}{suffix}"


def tprint(*args: Any, **kwargs: Any) -> None:
    """Print with a timestamp prefix and normalized tag order."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    message = " ".join(str(arg) for arg in args)
    formatted = _format_message(message)
    builtins.print(f"[{timestamp}]{formatted}", **kwargs)


def log(system: str, message: str, variant: str | None = None) -> None:
    """Log with explicit system and optional variant."""
    if variant:
        tprint(f"[{system}][{variant}] {message}")
    else:
        tprint(f"[{system}] {message}")
