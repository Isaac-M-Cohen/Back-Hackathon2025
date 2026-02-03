"""Executor interfaces and result payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from command_controller.fallback_chain import FallbackResult


@dataclass
class ExecutionResult:
    intent: str
    status: str
    target: str = "os"
    details: dict[str, Any] | None = None
    elapsed_ms: int | None = None

    # Optional web navigation metadata (enhanced executor features)
    resolved_url: str | None = None
    fallback_used: str | None = None
    navigation_time_ms: int | None = None
    dom_search_query: str | None = None

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

        # Include new fields only when present
        if self.resolved_url is not None:
            payload["resolved_url"] = self.resolved_url
        if self.fallback_used is not None:
            payload["fallback_used"] = self.fallback_used
        if self.navigation_time_ms is not None:
            payload["navigation_time_ms"] = self.navigation_time_ms
        if self.dom_search_query is not None:
            payload["dom_search_query"] = self.dom_search_query

        return payload


class BaseExecutor:
    def execute_step(self, step: dict) -> ExecutionResult:
        raise NotImplementedError


class ResolutionMetadataProvider(Protocol):
    """Protocol for executors that provide URL resolution metadata."""

    def get_last_resolution(self) -> FallbackResult | None:
        """Return metadata from the most recent URL resolution, if any."""
        ...

