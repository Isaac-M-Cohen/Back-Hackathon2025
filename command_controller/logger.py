"""Lightweight logger placeholder for command controller."""

import datetime as _dt


class CommandLogger:
    def _timestamp(self) -> str:
        return _dt.datetime.now().isoformat(timespec="seconds")

    def info(self, message: str) -> None:
        print(f"[{self._timestamp()}] [INFO] {message}")

    def error(self, message: str) -> None:
        print(f"[{self._timestamp()}] [ERROR] {message}")
