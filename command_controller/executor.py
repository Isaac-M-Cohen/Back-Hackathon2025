"""Executes mapped system actions."""

from __future__ import annotations

from command_controller.executors.base import ExecutionResult
from command_controller.executors.pyautogui_executor import PyAutoGUIExecutor
from command_controller.executors.router import OSRouter
from command_controller.intents import WebExecutionError
from utils.log_utils import tprint


# Intents that can be promoted to web target when following an open_url(target="web").
_WEB_CHAINABLE = {"type_text", "key_combo", "click", "scroll"}


class Executor:
    def __init__(self) -> None:
        self._web_executor = None  # lazy: WebExecutor
        self._router = OSRouter(fallback=PyAutoGUIExecutor())

    def execute(self, action: str, payload: dict) -> None:
        tprint(f"[EXECUTOR] Performing action='{action}' payload={payload}")

    def execute_steps(self, steps: list[dict]) -> list[dict]:
        steps = self._infer_web_targets(steps)
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

    @staticmethod
    def _infer_web_targets(steps: list[dict]) -> list[dict]:
        """Promote chainable intents to target='web' after an open_url with target='web'.

        Also drops wait_for_url steps inside web chains since Playwright handles
        page-load waiting natively.
        """
        in_web_chain = False
        out: list[dict] = []
        for step in steps:
            intent = step.get("intent", "")
            target = step.get("target")

            if intent == "open_url" and target == "web":
                in_web_chain = True
                out.append(step)
                continue

            if in_web_chain:
                if intent == "wait_for_url":
                    # Playwright handles waiting; skip this step.
                    continue
                if intent in _WEB_CHAINABLE:
                    step = {**step, "target": "web"}
                    out.append(step)
                    continue
                # Non-chainable intent breaks the web chain.
                in_web_chain = False

            out.append(step)
        return out

    def _get_web_executor(self):
        if self._web_executor is None:
            from command_controller.web_executor import WebExecutor
            self._web_executor = WebExecutor()
        return self._web_executor

    def _execute_web_step(self, step: dict) -> ExecutionResult:
        intent = str(step.get("intent", "")).strip() or "web"
        try:
            web_exec = self._get_web_executor()
            web_exec.execute_step(step)

            res_data = None
            if hasattr(web_exec, "get_last_resolution"):
                res_data = web_exec.get_last_resolution()

            if res_data:
                return ExecutionResult(
                    intent=intent,
                    status="ok",
                    target="web",
                    resolved_url=res_data.final_url,
                    fallback_used=res_data.fallback_used,
                    navigation_time_ms=res_data.elapsed_ms,
                    dom_search_query=(
                        res_data.resolution_details.search_query
                        if res_data.resolution_details
                        else None
                    ),
                )

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
