"""Executes mapped system actions."""

from __future__ import annotations

from command_controller.executors.base import ExecutionResult
from command_controller.executors.pyautogui_executor import PyAutoGUIExecutor
from command_controller.executors.router import OSRouter
from command_controller.intents import WebExecutionError
from utils.log_utils import tprint


class Executor:
    def __init__(self) -> None:
        self._web_executor = None  # lazy: WebExecutor
        self._router = OSRouter(fallback=PyAutoGUIExecutor())

    def execute(self, action: str, payload: dict) -> None:
        tprint(f"[EXECUTOR] Performing action='{action}' payload={payload}")

    def execute_steps(self, steps: list[dict]) -> list[dict]:
        results: list[dict] = []
        for step in steps:
            intent = str(step.get("intent", "")).strip()
            target = step.get("target") or ("web" if intent.startswith("web_") else "os")
            if target == "web":
                result = self._execute_web_step(step)
            else:
                result = self._router.execute_step(step)
            results.append(result.to_dict())
        return results

    def _get_web_executor(self):
        if self._web_executor is None:
            from command_controller.web_executor import WebExecutor
            self._web_executor = WebExecutor()
        return self._web_executor

    def _execute_web_step(self, step: dict) -> ExecutionResult:
        intent = str(step.get("intent", "")).strip() or "web"
        try:
            self._get_web_executor().execute_step(step)
            return ExecutionResult(intent=intent, status="ok", target="web")
        except WebExecutionError as exc:
            return ExecutionResult(
                intent=intent,
                status="failed",
                target="web",
                details={
                    "code": exc.code,
                    "reason": str(exc),
                    "screenshot_path": exc.screenshot_path,
                },
            )
