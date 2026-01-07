"""Collect UI context for command interpretation."""

from __future__ import annotations

import platform
import subprocess
import time
from typing import Any

from utils.runtime_state import get_client_os


def get_context(*, read_selection: bool = True) -> dict[str, Any]:
    """Return a snapshot of the current UI context."""
    context: dict[str, Any] = {
        "platform": platform.system(),
        "client_os": get_client_os(),
        "mouse_position": None,
        "active_window": None,
        "selection_text": None,
        "selection_length": 0,
    }
    context["mouse_position"] = _mouse_position()
    context["active_window"] = _active_window_title()
    if read_selection:
        selection = _read_selection_text()
        if selection:
            context["selection_text"] = selection
            context["selection_length"] = len(selection)
    return context


def _mouse_position() -> dict[str, int] | None:
    try:
        import pyautogui

        pos = pyautogui.position()
        return {"x": int(pos.x), "y": int(pos.y)}
    except Exception:
        return None


def _active_window_title() -> str | None:
    try:
        import pyautogui

        win = pyautogui.getActiveWindow()
        if win and getattr(win, "title", None):
            return str(win.title)
    except Exception:
        pass
    return None


def _read_selection_text() -> str | None:
    """Try to copy selection and read it without changing clipboard permanently."""
    clipboard_before = _read_clipboard()
    copied = _copy_selection()
    if not copied:
        return clipboard_before
    time.sleep(0.06)
    clipboard_after = _read_clipboard()
    if clipboard_before is not None and clipboard_after != clipboard_before:
        _write_clipboard(clipboard_before)
    return clipboard_after


def _copy_selection() -> bool:
    try:
        import pyautogui

        client_os = get_client_os()
        effective_os = client_os or platform.system()
        modifier = "command" if effective_os == "Darwin" else "ctrl"
        pyautogui.hotkey(modifier, "c")
        return True
    except Exception:
        return False


def _read_clipboard() -> str | None:
    try:
        import pyperclip

        return pyperclip.paste()
    except Exception:
        pass
    if platform.system() == "Darwin":
        return _run_clipboard_cmd(["pbpaste"])
    if platform.system() == "Windows":
        return _run_clipboard_cmd(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"]
        )
    return _run_clipboard_cmd(["xclip", "-selection", "clipboard", "-o"])


def _write_clipboard(text: str) -> None:
    try:
        import pyperclip

        pyperclip.copy(text)
        return
    except Exception:
        pass
    if platform.system() == "Darwin":
        _run_clipboard_cmd(["pbcopy"], input_text=text)
        return
    if platform.system() == "Windows":
        _run_clipboard_cmd(
            ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value @'\n" + text + "\n'@"]
        )
        return
    _run_clipboard_cmd(["xclip", "-selection", "clipboard"], input_text=text)


def _run_clipboard_cmd(cmd: list[str], input_text: str | None = None) -> str | None:
    try:
        proc = subprocess.run(
            cmd,
            input=input_text.encode("utf-8") if input_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        output = proc.stdout.decode("utf-8", errors="ignore").strip()
        return output if output else None
    except Exception:
        return None
