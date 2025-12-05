"""Very small event bus for inter-module communication."""

from collections import defaultdict
from collections.abc import Callable


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Callable) -> None:
        self._subscribers[topic].append(handler)

    def publish(self, topic: str, payload: dict | None = None) -> None:
        for handler in self._subscribers.get(topic, []):
            handler(payload or {})
