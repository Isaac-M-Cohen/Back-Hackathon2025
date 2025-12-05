"""System helpers for environment checks."""

import platform


def current_os() -> str:
    return platform.system().lower()


def is_macos() -> bool:
    return current_os() == "darwin"


def is_windows() -> bool:
    return current_os().startswith("windows")


def is_linux() -> bool:
    return current_os() == "linux"
