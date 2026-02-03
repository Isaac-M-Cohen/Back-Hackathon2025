"""Route intents to OS-native executors with fallback."""

from __future__ import annotations

import platform

from command_controller.executors.base import BaseExecutor, ExecutionResult
from command_controller.executors.macos_executor import MacOSExecutor
from command_controller.executors.windows_executor import WindowsExecutor
from utils.runtime_state import get_client_os


class OSRouter(BaseExecutor):
    def __init__(self, *, fallback: BaseExecutor | None = None) -> None:
        self._macos = MacOSExecutor()
        self._windows = WindowsExecutor()
        self._fallback = fallback

    def execute_step(self, step: dict) -> ExecutionResult:
        os_name = get_client_os() or platform.system()
        if os_name == "Darwin":
            primary = self._macos
        elif os_name == "Windows":
            primary = self._windows
        else:
            primary = None

        if primary:
            result = primary.execute_step(step)
            if result.status in {"unsupported", "not_implemented"} and self._fallback:
                fallback_result = self._fallback.execute_step(step)
                if fallback_result.details is None:
                    fallback_result.details = {}
                fallback_result.details["fallback_from"] = os_name
                return fallback_result
            return result

        if self._fallback:
            return self._fallback.execute_step(step)

        intent = str(step.get("intent", "")).strip() or "unknown"
        return ExecutionResult(
            intent=intent,
            status="unsupported",
            target=step.get("target", "os"),
            details={"reason": f"Unsupported OS {os_name}"},
        )

