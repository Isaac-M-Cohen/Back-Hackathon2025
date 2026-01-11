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
from utils.settings_store import is_deep_logging


SENSITIVE_PATTERNS = re.compile(
    r"\\b(delete|remove|erase|trash|format|wipe|rm\\b|shutdown|restart|kill|terminate|uninstall)\\b",
    re.IGNORECASE,
)


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

    def run(self, *, source: str, text: str, context: dict | None = None) -> dict:
        if not text.strip():
            return {"status": "ignored", "reason": "empty"}

        try:
            start = time.monotonic()
            payload = self._parse_text(text, context or {})
            steps = validate_steps(self._insert_wait_for_url(normalize_steps(payload)))
            elapsed_ms = (time.monotonic() - start) * 1000.0
            self.logger.info(f"LLM parse time: {elapsed_ms:.0f} ms")
            if is_deep_logging():
                print(f"[DEEP][ENGINE] parsed payload={payload} steps={steps}")
        except (ValueError, LocalLLMError) as exc:
            self.logger.error(f"Command parse failed: {exc}")
            return {"status": "error", "reason": str(exc)}

        if not steps:
            return {"status": "ignored", "reason": "no_steps"}

        if self._requires_confirmation(text, steps):
            pending = self.confirmations.create(
                source=source,
                text=text,
                reason="Sensitive command requires confirmation",
                intents=steps,
            )
            self.logger.info(f"Command pending confirmation: {pending.id}")
            return {"status": "pending", "id": pending.id}

        self.executor.execute_steps(steps)
        return {"status": "ok"}

    def run_steps(self, *, source: str, text: str, steps: list[dict]) -> dict:
        if not steps:
            return {"status": "ignored", "reason": "no_steps"}

        try:
            cleaned_steps = validate_steps(steps)
        except ValueError as exc:
            self.logger.error(f"Command steps invalid: {exc}")
            return {"status": "error", "reason": str(exc)}
        if is_deep_logging():
            print(f"[DEEP][ENGINE] run_steps cleaned_steps={cleaned_steps}")

        if self._requires_confirmation(text, cleaned_steps):
            pending = self.confirmations.create(
                source=source,
                text=text,
                reason="Sensitive command requires confirmation",
                intents=cleaned_steps,
            )
            self.logger.info(f"Command pending confirmation: {pending.id}")
            return {"status": "pending", "id": pending.id}

        self.executor.execute_steps(cleaned_steps)
        return {"status": "ok"}

    def approve(self, confirmation_id: str) -> dict:
        pending = self.confirmations.pop(confirmation_id)
        if not pending:
            return {"status": "missing"}
        self.executor.execute_steps(pending.intents)
        return {"status": "ok"}

    def deny(self, confirmation_id: str) -> dict:
        pending = self.confirmations.pop(confirmation_id)
        if not pending:
            return {"status": "missing"}
        return {"status": "denied"}

    def list_pending(self) -> list[dict]:
        return [item.to_dict() for item in self.confirmations.list()]

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

    def _insert_wait_for_url(self, steps: list[dict]) -> list[dict]:
        if not steps:
            return steps
        updated: list[dict] = []
        pending_url: str | None = None
        for step in steps:
            intent = step.get("intent")
            if intent == "open_url":
                pending_url = str(step.get("url", "")).strip() or None
                updated.append(step)
                continue
            if pending_url and intent == "wait_for_url":
                pending_url = None
                updated.append(step)
                continue
            if pending_url and intent == "type_text":
                updated.append(
                    {
                        "intent": "wait_for_url",
                        "url": pending_url,
                        "timeout_secs": 15,
                        "interval_secs": 0.5,
                    }
                )
                pending_url = None
            updated.append(step)
        return updated

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
            if step.get("intent") == "type_text" and SENSITIVE_PATTERNS.search(step.get("text", "")):
                return True
        return False
