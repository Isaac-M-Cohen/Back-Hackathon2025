"""Entry point for the hand + voice control system."""

import importlib.util
import os
import sys
from pathlib import Path

try:  # Optional dependency; enable .env loading when available.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dep
    load_dotenv = None

def _ensure_qt_plugin_path() -> None:
    """Set Qt plugin paths before importing PySide6-based modules."""
    if os.getenv("QT_QPA_PLATFORM_PLUGIN_PATH"):
        return
    spec = importlib.util.find_spec("PySide6")
    if not spec or not spec.submodule_search_locations:
        return
    pyside_root = Path(spec.submodule_search_locations[0])
    plugin_root = pyside_root / "Qt" / "plugins"
    platforms_path = plugin_root / "platforms"
    if platforms_path.exists():
        os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(platforms_path))
        os.environ.setdefault("QT_PLUGIN_PATH", str(plugin_root))


_ensure_qt_plugin_path()

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

def _load_env_files() -> None:
    """Load .env files from common locations (repo, bundle, home)."""
    if not load_dotenv:
        return

    candidates: list[Path] = []
    cwd = Path.cwd()
    candidates.extend([cwd / "env/.env", cwd / ".env"])

    module_root = Path(__file__).resolve().parent
    candidates.extend([module_root / "env/.env", module_root / ".env"])

    home = Path.home()
    candidates.extend([home / ".easy.env", home / ".env.easy"])

    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        if meipass:
            candidates.extend([meipass / "env/.env", meipass / ".env"])
        exec_path = Path(sys.executable).resolve()
        resources = exec_path.parent.parent / "Resources"
        candidates.extend([resources / "env/.env", resources / ".env"])

    for path in candidates:
        if path.exists():
            load_dotenv(dotenv_path=str(path), override=False)


def bootstrap() -> None:
    """Wire up core modules and start listeners."""
    _load_env_files()

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

    controller.start()
    # Voice can still run headless; camera stays closed unless UI invokes workflow.
    if voice:
        voice.start()

    main_window = MainWindow(gesture_workflow=gesture_workflow, controller=controller)
    try:
        main_window.launch()
    except KeyboardInterrupt:
        print("[MAIN] Received interrupt. Shutting down...")
    finally:
        if voice and voice.is_running():
            voice.stop()


if __name__ == "__main__":
    bootstrap()
