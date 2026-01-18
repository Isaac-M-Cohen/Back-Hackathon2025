"""Lightweight logger placeholder for command controller."""

from utils.log_utils import log


class CommandLogger:
    def info(self, message: str) -> None:
        log("CMD", message, "INFO")

    def error(self, message: str) -> None:
        log("CMD", message, "ERROR")
