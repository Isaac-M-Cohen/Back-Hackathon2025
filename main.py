"""Entry point for the desktop app (Tauri + React)."""

import os
import subprocess
import sys
from pathlib import Path

try:  # Optional dependency; enable .env loading when available.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dep
    load_dotenv = None

def _ensure_python_version() -> None:
    """Raise early if Python version is not 3.11.x (required by MediaPipe)."""
    if (ver := sys.version_info)[:2] != (3, 11):
        raise RuntimeError(
            f"Python 3.11.x required for MediaPipe compatibility (found {ver.major}.{ver.minor})."
        )


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


def _run_tauri(command: str = "tauri:dev") -> None:
    """Launch the Tauri desktop app (React UI + Python backend sidecar)."""
    webui_dir = Path(__file__).resolve().parent / "webui"
    if not webui_dir.exists():
        raise RuntimeError(f"Missing webui directory at {webui_dir}")

    env = os.environ.copy()
    env.setdefault("EASY_PYTHON_BIN", sys.executable)
    cargo_bin = str(Path.home() / ".cargo" / "bin")
    if cargo_bin not in env.get("PATH", ""):
        env["PATH"] = f"{cargo_bin}:{env.get('PATH', '')}"

    cmd = ["npm", "run", command]
    subprocess.run(cmd, cwd=webui_dir, env=env, check=True)


def bootstrap() -> None:
    """Load env files and run the Tauri desktop app."""
    _load_env_files()
    _ensure_python_version()
    tauri_command = os.getenv("EASY_TAURI_COMMAND", "tauri:dev")
    _run_tauri(tauri_command)


if __name__ == "__main__":
    bootstrap()
