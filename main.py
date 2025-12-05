"""Entry point for the hand + voice control system."""

from command_controller.controller import CommandController
from gesture_module.gesture_detector import GestureDetector
from voice_module.voice_listener import VoiceListener


def bootstrap() -> None:
    """Wire up core modules and start listeners."""
    controller = CommandController()
    gestures = GestureDetector(controller)
    voice = VoiceListener(controller)

    # TODO: replace with real event loop and UI launch.
    controller.start()
    gestures.start()
    voice.start()


if __name__ == "__main__":
    bootstrap()
