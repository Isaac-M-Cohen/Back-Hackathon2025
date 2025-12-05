"""Placeholder for hand tracking backend (e.g., MediaPipe)."""


class HandTracker:
    def __init__(self) -> None:
        self.active = False

    def start(self) -> None:
        self.active = True
        print("[HAND] Tracking started")

    def stop(self) -> None:
        self.active = False
        print("[HAND] Tracking stopped")
