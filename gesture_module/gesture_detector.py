"""Detects gestures and forwards them to the command controller."""

from command_controller.controller import CommandController
from gesture_module.hand_tracking import HandTracker


class GestureDetector:
    def __init__(self, controller: CommandController) -> None:
        self.controller = controller
        self.tracker = HandTracker()

    def start(self) -> None:
        """Begin processing gestures (placeholder implementation)."""
        print("[GESTURE] Detector initialized")
        # Example: simulate a swipe event
        self.controller.handle_event(source="gesture", action="swipe_right")
