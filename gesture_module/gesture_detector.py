"""Detects gestures and forwards them to the command controller."""

from command_controller.controller import CommandController
from gesture_module.hand_tracking import HandTracker


class GestureDetector:
    def __init__(self, controller: CommandController, config_path: str = "config/gesture_config.json") -> None:
        self.controller = controller
        self.tracker = HandTracker(config_path=config_path)

    def start(self) -> None:
        """Start hand tracking and landmark visualization."""
        print("[GESTURE] Detector starting hand tracker")
        self.tracker.start()
