"""Helpers for running modules concurrently."""

import threading
from collections.abc import Callable


def run_async(target: Callable, *, daemon: bool = True) -> threading.Thread:
    thread = threading.Thread(target=target, daemon=daemon)
    thread.start()
    return thread
