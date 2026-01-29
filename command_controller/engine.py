"""Command interpretation and execution pipeline."""

from __future__ import annotations

import platform
import re
import time
from typing import Iterable

from command_controller.confirmations import ConfirmationStore
from command_controller.executor import Executor
from command_controller.intents import normalize_steps, validate_steps
from command_controller.llm import LocalLLMInterpreter, LocalLLMError
from command_controller.logger import CommandLogger
from utils.settings_store import deep_log


SENSITIVE_PATTERNS = re.compile(
    r"\\b(delete|remove|erase|trash|format|wipe|rm\\b|shutdown|restart|kill|terminate|uninstall)\\b",
    re.IGNORECASE,
)

ALWAYS_CONFIRM_INTENTS = {"web_send_message"}


class CommandEngine:
    def __init__(
        self,
        *,
        interpreter: LocalLLMInterpreter | None = None,
        executor: Executor | None = None,
        confirmations: ConfirmationStore | None = None,
        logger: CommandLogger | None = None,
    ) -> None:
        self.interpreter = interpreter or LocalLLMInterpreter()
        self.executor = executor or Executor()
        self.confirmations = confirmations or ConfirmationStore()
        self.logger = logger or CommandLogger()
        self._last_result: dict | None = None

    def run(self, *, source: str, text: str, context: dict | None = None) -> dict:
        if not text.strip():
            result = {"status": "ignored", "reason": "empty"}
            self._store_result(result)
            return result

        try:
            start = time.monotonic()
            payload = self._parse_text(text, context or {})
            steps = validate_steps(normalize_steps(payload))
            elapsed_ms = (time.monotonic() - start) * 1000.0
            self.logger.info(f"LLM parse time: {elapsed_ms:.0f} ms")
            deep_log(f"[DEEP][ENGINE] parsed payload={payload} steps={steps}")
        except (ValueError, LocalLLMError) as exc:
            self.logger.error(f"Command parse failed: {exc}")
            result = {"status": "error", "reason": str(exc)}
            self._store_result(result)
            return result

        if not steps:
            result = {"status": "ignored", "reason": "no_steps"}
            self._store_result(result)
            return result

        if self._requires_confirmation(text, steps):
            pending = self.confirmations.create(
                source=source,
                text=text,
                reason="Sensitive command requires confirmation",
                intents=steps,
            )
            self.logger.info(f"Command pending confirmation: {pending.id}")
            result = {"status": "pending", "id": pending.id}
            self._store_result(result)
            return result

        return self._safe_execute(steps)

    def run_steps(self, *, source: str, text: str, steps: list[dict]) -> dict:
        if not steps:
            result = {"status": "ignored", "reason": "no_steps"}
            self._store_result(result)
            return result

        try:
            cleaned_steps = validate_steps(steps)
        except ValueError as exc:
            self.logger.error(f"Command steps invalid: {exc}")
            result = {"status": "error", "reason": str(exc)}
            self._store_result(result)
            return result
        deep_log(f"[DEEP][ENGINE] run_steps cleaned_steps={cleaned_steps}")

        if self._requires_confirmation(text, cleaned_steps):
            pending = self.confirmations.create(
                source=source,
                text=text,
                reason="Sensitive command requires confirmation",
                intents=cleaned_steps,
            )
            self.logger.info(f"Command pending confirmation: {pending.id}")
            result = {"status": "pending", "id": pending.id}
            self._store_result(result)
            return result

        return self._safe_execute(cleaned_steps)

    def approve(self, confirmation_id: str) -> dict:
        pending = self.confirmations.pop(confirmation_id)
        if not pending:
            result = {"status": "missing"}
            self._store_result(result)
            return result
        return self._safe_execute(pending.intents)

    def deny(self, confirmation_id: str) -> dict:
        pending = self.confirmations.pop(confirmation_id)
        if not pending:
            result = {"status": "missing"}
            self._store_result(result)
            return result
        result = {"status": "denied"}
        self._store_result(result)
        return result

    def _safe_execute(self, steps: list[dict]) -> dict:
        """Execute steps, catching web execution errors."""
        try:
            results = self.executor.execute_steps(steps)
            result = {"status": "ok", "results": results}
            self._store_result(result)
            return result
        except Exception as exc:
            self.logger.error(f"Execution failed: {exc}")
            error_info: dict = {"status": "error", "reason": str(exc)}
            if hasattr(exc, "code"):
                error_info["code"] = exc.code
            if hasattr(exc, "screenshot_path") and exc.screenshot_path:
                error_info["screenshot"] = exc.screenshot_path
            self._store_result(error_info)
            return error_info

    def list_pending(self) -> list[dict]:
        return [item.to_dict() for item in self.confirmations.list()]

    def get_last_result(self) -> dict | None:
        return self._last_result

    def _store_result(self, result: dict) -> None:
        payload = dict(result)
        payload["timestamp"] = time.time()
        self._last_result = payload

    def _parse_text(self, text: str, context: dict) -> dict | list:
        stripped = text.strip()
        shortcut = self._shortcut_for_text(stripped)
        if shortcut:
            self.logger.info(f"Shortcut match: '{stripped}' -> {shortcut.get('keys')}")
            return {"steps": [shortcut]}
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                import json

                return json.loads(stripped)
            except json.JSONDecodeError:
                pass
        self.logger.info(f"LLM interpret: '{stripped}'")
        return self.interpreter.interpret(text, context)

    def _shortcut_for_text(self, text: str) -> dict | None:
        normalized = text.lower().strip()
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
        normalized = " ".join(normalized.split())
        if not normalized:
            return None
        modifier = "command" if platform.system() == "Darwin" else "ctrl"
        shortcuts = {
            "copy": [modifier, "c"],
            "copy selection": [modifier, "c"],
            "copy selected text": [modifier, "c"],
            "paste": [modifier, "v"],
            "paste selection": [modifier, "v"],
            "cut": [modifier, "x"],
            "cut selection": [modifier, "x"],
            "undo": [modifier, "z"],
            "redo": [modifier, "shift", "z"] if modifier == "cmd" else [modifier, "y"],
            "select all": [modifier, "a"],
        }
        keys = shortcuts.get(normalized)
        if not keys:
            return None
        return {"intent": "key_combo", "keys": keys}

    def _requires_confirmation(self, text: str, steps: Iterable[dict]) -> bool:
        if SENSITIVE_PATTERNS.search(text):
            return True
        for step in steps:
            intent = step.get("intent", "")
            if intent in ALWAYS_CONFIRM_INTENTS:
                return True
            if intent == "type_text" and SENSITIVE_PATTERNS.search(step.get("text", "")):
                return True
        return False
