"""Entry point for the hand + voice control system."""

import sys

from command_controller.controller import CommandController
from gesture_module.gesture_detector import GestureDetector
from voice_module.voice_listener import VoiceListener


def _ensure_python_version() -> None:
    """Raise early if Python version is not 3.11.x (required by MediaPipe)."""
    if (ver := sys.version_info)[:2] != (3, 11):
        raise RuntimeError(
            f"Python 3.11.x required for MediaPipe compatibility (found {ver.major}.{ver.minor})."
        )


def bootstrap() -> None:
    """Wire up core modules and start listeners."""
    _ensure_python_version()
    controller = CommandController()
    gestures = GestureDetector(controller)
    voice = VoiceListener(controller)

    # TODO: replace with real event loop and UI launch.
    controller.start()
    gestures.start()
    voice.start()


if __name__ == "__main__":
    bootstrap()
