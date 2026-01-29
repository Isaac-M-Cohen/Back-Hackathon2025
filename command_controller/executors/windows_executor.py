"""Windows-native executor using ShellExecute-style launches."""

from __future__ import annotations

import subprocess
import time

from command_controller.executors.base import BaseExecutor, ExecutionResult
from utils.settings_store import deep_log, is_deep_logging


class WindowsExecutor(BaseExecutor):
    def execute_step(self, step: dict) -> ExecutionResult:
        intent = str(step.get("intent", "")).strip()
        start = time.monotonic()
        target = step.get("target", "os")

        try:
            if intent == "open_url":
                url = str(step.get("url", "")).strip()
                if not url:
                    return self._failed(intent, target, "missing url", start)
                self._start(url)
                return self._ok(intent, target, start)

            if intent == "open_app":
                app = str(step.get("app", "")).strip()
                if not app:
                    return self._failed(intent, target, "missing app", start)
                self._start(app)
                return self._ok(intent, target, start)

            if intent == "open_file":
                path = str(step.get("path", "")).strip()
                if not path:
                    return self._failed(intent, target, "missing path", start)
                self._start(path)
                return self._ok(intent, target, start)

            if intent in {"find_ui", "invoke_ui", "wait_for_window"}:
                return self._unsupported(intent, target, "UI automation not implemented", start)

            return self._unsupported(intent, target, "unsupported intent", start)
        except Exception as exc:
            return self._failed(intent, target, str(exc), start)

    def _start(self, target: str) -> None:
        if is_deep_logging():
            deep_log(f"[DEEP][WIN_EXEC] start target={target}")
        subprocess.Popen(
            ["cmd", "/c", "start", "", target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True,
        )

    def _ok(self, intent: str, target: str, start: float) -> ExecutionResult:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return ExecutionResult(intent=intent, status="ok", target=target, elapsed_ms=elapsed_ms)

    def _failed(self, intent: str, target: str, reason: str, start: float) -> ExecutionResult:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return ExecutionResult(
            intent=intent,
            status="failed",
            target=target,
            details={"reason": reason},
            elapsed_ms=elapsed_ms,
        )

    def _unsupported(self, intent: str, target: str, reason: str, start: float) -> ExecutionResult:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return ExecutionResult(
            intent=intent,
            status="unsupported",
            target=target,
            details={"reason": reason},
            elapsed_ms=elapsed_ms,
        )

