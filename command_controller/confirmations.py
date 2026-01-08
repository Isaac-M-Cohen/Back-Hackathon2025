"""In-memory store for pending command confirmations."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
import threading
import uuid
from typing import Iterable


@dataclass
class PendingConfirmation:
    id: str
    source: str
    text: str
    reason: str
    intents: list[dict]
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class ConfirmationStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, PendingConfirmation] = {}

    def create(self, source: str, text: str, reason: str, intents: list[dict]) -> PendingConfirmation:
        confirmation = PendingConfirmation(
            id=str(uuid.uuid4()),
            source=source,
            text=text,
            reason=reason,
            intents=intents,
            created_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        )
        with self._lock:
            self._pending[confirmation.id] = confirmation
        return confirmation

    def list(self) -> list[PendingConfirmation]:
        with self._lock:
            return list(self._pending.values())

    def pop(self, confirmation_id: str) -> PendingConfirmation | None:
        with self._lock:
            return self._pending.pop(confirmation_id, None)

    def clear(self) -> None:
        with self._lock:
            self._pending.clear()
