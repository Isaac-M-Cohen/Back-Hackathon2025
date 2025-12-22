"""Entry point for the hand + voice control system."""

import sys
import os
import time

try:  # Optional dependency; enable .env loading when available.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dep
    load_dotenv = None

from command_controller.controller import CommandController
from gesture_module.gesture_recognizer import RealTimeGestureRecognizer
from voice_module.voice_listener import VoiceListener


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
    gestures = None
    if _is_enabled("ENABLE_GESTURES", True):
        try:
            gestures = RealTimeGestureRecognizer(
                controller,
                user_id=os.getenv("GESTURE_USER_ID", "default"),
                confidence_threshold=float(os.getenv("GESTURE_CONFIDENCE", "0.6")),
                stable_frames=int(os.getenv("GESTURE_STABLE_FRAMES", "5")),
            )
        except Exception as exc:
            print(f"[MAIN] Gesture recognizer unavailable: {exc}")
            gestures = None
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
    if voice:
        voice.start()
    if gestures:
        # Run gestures on main thread when voice is disabled to avoid OpenCV/GUI
        # issues on macOS; otherwise start in background for concurrency.
        if voice is None:
            gestures.start_blocking()
        else:
            gestures.start()

    try:

        if not voice and not gestures:
            print("[MAIN] No input modules enabled (set ENABLE_VOICE and/or ENABLE_GESTURES).")
            return

        while True:
            voice_alive = voice.is_running() if voice else False
            gesture_alive = gestures.is_running() if gestures else False

            if not voice_alive and not gesture_alive:
                break
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("[MAIN] Received interrupt. Shutting down...")
    finally:
        if voice and voice.is_running():
            voice.stop()
        if gestures and gestures.is_running():
            gestures.stop()


if __name__ == "__main__":
    bootstrap()
