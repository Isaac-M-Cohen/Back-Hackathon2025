"""Executor interfaces and result payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ExecutionResult:
    intent: str
    status: str
    target: str = "os"
    details: dict[str, Any] | None = None
    elapsed_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "intent": self.intent,
            "status": self.status,
            "target": self.target,
        }
        if self.details is not None:
            payload["details"] = self.details
        if self.elapsed_ms is not None:
            payload["elapsed_ms"] = self.elapsed_ms
        return payload


class BaseExecutor:
    def execute_step(self, step: dict) -> ExecutionResult:
        raise NotImplementedError

