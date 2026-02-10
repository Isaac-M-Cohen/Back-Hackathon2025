"""Executes mapped system actions."""

from __future__ import annotations

import re

from command_controller.executors.base import ExecutionResult
from command_controller.executors.pyautogui_executor import PyAutoGUIExecutor
from command_controller.executors.router import OSRouter
from command_controller.intents import WebExecutionError
from command_controller.web_constants import COMMON_DOMAINS
from utils.log_utils import tprint
from utils.settings_store import deep_log, is_deep_logging


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
        for index, step in enumerate(steps):
            intent = str(step.get("intent", "")).strip()
            target = step.get("target") or ("web" if intent.startswith("web_") else "os")
            if is_deep_logging():
                deep_log(f"[DEEP][EXECUTOR] step index={index} intent={intent} target={target} step={step}")
            if target == "web":
                result = self._execute_web_step(step)
            else:
                result = self._router.execute_step(step)
            if is_deep_logging():
                deep_log(f"[DEEP][EXECUTOR] step index={index} result={result.to_dict()}")
            results.append(result.to_dict())
        if self._web_executor is not None and hasattr(self._web_executor, "flush_deferred_open"):
            self._web_executor.flush_deferred_open()
        return results


    @staticmethod
    def _infer_web_targets(steps: list[dict]) -> list[dict]:
        """Promote chainable intents to target='web' after an open_url with target='web'.

        Also drops wait_for_url steps inside web chains since Playwright handles
        page-load waiting natively.
        """
        in_web_chain = False
        out: list[dict] = []
        for idx, step in enumerate(steps):
            intent = step.get("intent", "")
            target = step.get("target")

            if intent == "open_app":
                if Executor._should_promote_open_app(steps, idx):
                    url = Executor._app_to_url(step.get("app", ""))
                    if url:
                        next_step = steps[idx + 1] if idx + 1 < len(steps) else None
                        web_step = {"intent": "open_url", "url": url, "target": "web"}
                        if next_step and next_step.get("intent") in _WEB_CHAINABLE:
                            web_step["defer_open"] = True
                        in_web_chain = True
                        out.append(web_step)
                        continue

            if intent == "open_url" and target == "web":
                in_web_chain = True
                next_step = steps[idx + 1] if idx + 1 < len(steps) else None
                if next_step and next_step.get("intent") in _WEB_CHAINABLE:
                    step = {**step, "defer_open": True}
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

    @staticmethod
    def _should_promote_open_app(steps: list[dict], idx: int) -> bool:
        for future in steps[idx + 1 :]:
            intent = str(future.get("intent", "")).strip()
            target = future.get("target")
            if target == "web" or intent.startswith("web_"):
                return True
        return False

    @staticmethod
    def _app_to_url(app: str) -> str | None:
        key = str(app or "").strip().lower()
        if not key:
            return None
        if key in COMMON_DOMAINS:
            return f"https://{COMMON_DOMAINS[key]}"
        if " " in key:
            return None
        slug = re.sub(r"[^a-z0-9]+", "", key)
        if not slug:
            return None
        return f"https://{slug}.com"

    def _get_web_executor(self):
        if self._web_executor is None:
            from command_controller.web_executor import WebExecutor
            self._web_executor = WebExecutor()
        return self._web_executor

    def prewarm_web(self, steps: list[dict]) -> None:
        """Warm the web executor if any web-target steps are present."""
        if not any(
            (step.get("target") == "web")
            or str(step.get("intent", "")).startswith("web_")
            for step in steps
        ):
            return
        web_exec = self._get_web_executor()
        if hasattr(web_exec, "warmup_for_steps"):
            web_exec.warmup_for_steps(steps)

    def resolve_web_steps(self, steps: list[dict]) -> dict:
        """Resolve web steps into a direct URL for instant execution."""
        if not any(
            (step.get("target") == "web")
            or str(step.get("intent", "")).startswith("web_")
            for step in steps
        ):
            return {}
        web_exec = self._get_web_executor()
        if hasattr(web_exec, "resolve_web_steps"):
            return web_exec.resolve_web_steps(steps)
        return {}

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
