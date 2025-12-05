"""Utility helpers for gesture calculations."""

from collections.abc import Iterable


def smooth(values: Iterable[float], window: int = 5) -> float:
    values = list(values)
    if not values:
        return 0.0
    window = max(1, window)
    return sum(values[-window:]) / min(len(values), window)
