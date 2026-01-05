"""Command interpretation and execution pipeline."""

from __future__ import annotations

import re
from typing import Iterable

from command_controller.confirmations import ConfirmationStore
from command_controller.executor import Executor
from command_controller.intents import normalize_steps, validate_steps
from command_controller.llm import LocalLLMInterpreter, LocalLLMError
from command_controller.logger import CommandLogger


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

    def run(self, *, source: str, text: str) -> dict:
        if not text.strip():
            return {"status": "ignored", "reason": "empty"}

        try:
            payload = self._parse_text(text)
            steps = validate_steps(normalize_steps(payload))
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

    def _parse_text(self, text: str) -> dict | list:
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                import json

                return json.loads(stripped)
            except json.JSONDecodeError:
                pass
        return self.interpreter.interpret(text)

    def _requires_confirmation(self, text: str, steps: Iterable[dict]) -> bool:
        if SENSITIVE_PATTERNS.search(text):
            return True
        for step in steps:
            if step.get("intent") == "type_text" and SENSITIVE_PATTERNS.search(step.get("text", "")):
                return True
        return False
