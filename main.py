"""Entry point for the hand + voice control system."""

import sys
import os
import time

try:  # Optional dependency; enable .env loading when available.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dep
    load_dotenv = None

from command_controller.controller import CommandController
from gesture_module.workflow import GestureWorkflow
from voice_module.voice_listener import VoiceListener
from ui.main_window import MainWindow


def _ensure_python_version() -> None:
    """Raise early if Python version is not 3.11.x (required by MediaPipe)."""
    if (ver := sys.version_info)[:2] != (3, 11):
        raise RuntimeError(
            f"Python 3.11.x required for MediaPipe compatibility (found {ver.major}.{ver.minor})."
        )


def _is_enabled(name: str, default: bool = True) -> bool:
    """Read a boolean-like environment variable (1/0/true/false)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def bootstrap() -> None:
    """Wire up core modules and start listeners."""
    if load_dotenv:
        load_dotenv(dotenv_path="env/.env", override=False)

    _ensure_python_version()
    controller = CommandController()
    gesture_workflow = GestureWorkflow(
        user_id=os.getenv("GESTURE_USER_ID", "default"),
        window_size=int(os.getenv("GESTURE_WINDOW", "30")),
    )
    single_batch_voice = _is_enabled("VOICE_SINGLE_BATCH", False)
    log_token_usage = _is_enabled("LOG_TOKEN_USAGE", False)
    voice = (
        VoiceListener(
            controller,
            single_batch=single_batch_voice,
            log_token_usage=log_token_usage,
        )
        if _is_enabled("ENABLE_VOICE", True)
        else None
    )

    # TODO: replace with real event loop and UI launch.
    controller.start()
    main_window = MainWindow(gesture_workflow=gesture_workflow)
    main_window.launch()
    # Voice can still run headless; camera stays closed unless UI invokes workflow.
    if voice:
        voice.start()

    try:

        if not voice:
            print("[MAIN] Voice disabled; UI controls gestures manually.")
            while main_window.is_open:
                time.sleep(0.2)
            return

        while True:
            voice_alive = voice.is_running() if voice else False
            # Gestures are controlled via UI; check if app is still open.

            if not voice_alive or not main_window.is_open:
                break
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("[MAIN] Received interrupt. Shutting down...")
    finally:
        if voice and voice.is_running():
            voice.stop()


if __name__ == "__main__":
    bootstrap()
