"""Detects gestures and forwards them to the command controller."""
import threading

from utils.log_utils import tprint

from command_controller.controller import CommandController
from gesture_module.hand_tracking import HandTracker


class GestureDetector:
    def __init__(self, controller: CommandController, config_path: str = "config/gesture_config.json") -> None:
        self.controller = controller
        self.tracker = HandTracker(config_path=config_path)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start hand tracking on a separate thread (non-blocking)."""
        if self._thread and self._thread.is_alive():
            tprint("[GESTURE] Detector already running (background)")
            return
        if self.tracker.active:
            tprint("[GESTURE] Detector already running")
            return

        def _runner() -> None:
            try:
                self.tracker.start()
            except Exception as exc:  # pragma: no cover - surface runtime issues
                tprint(f"[GESTURE] Detector error: {exc}")

        self._thread = threading.Thread(target=_runner, name="GestureDetector", daemon=False)
        self._thread.start()

    def start_blocking(self) -> None:
        """Start hand tracking and block until exit."""
        if self.tracker.active:
            tprint("[GESTURE] Detector already running")
            return
        tprint("[GESTURE] Detector starting hand tracker")
        self.tracker.start()

    def stop(self) -> None:
        """Stop tracking and join background thread if present."""
        self.tracker.stop()
        if self._thread:
            self._thread.join(timeout=2)

    def is_running(self) -> bool:
        return bool((self._thread and self._thread.is_alive()) or self.tracker.active)
