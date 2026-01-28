"""Executes mapped system actions."""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser

from utils.log_utils import tprint
from utils.settings_store import deep_log, get_settings, is_deep_logging


class Executor:
    def __init__(self) -> None:
        self._last_opened_url: str | None = None
        self._intent_handlers = {
            "open_url": self._handle_open_url,
            "wait_for_url": self._handle_wait_for_url,
            "open_app": self._handle_open_app,
            "key_combo": self._handle_key_combo,
            "type_text": self._handle_type_text,
            "scroll": self._handle_scroll,
            "mouse_move": self._handle_mouse_move,
            "click": self._handle_click,
        }

    def execute(self, action: str, payload: dict) -> None:
        tprint(f"[EXECUTOR] Performing action='{action}' payload={payload}")

    def execute_steps(self, steps: list[dict]) -> None:
        for step in steps:
            self.execute_step(step)

    def execute_step(self, step: dict) -> None:
        intent = step.get("intent")
        handler = self._intent_handlers.get(intent)
        if handler:
            handler(step)
            return
        tprint(f"[EXECUTOR] Unknown intent '{intent}'")

    def _handle_open_url(self, step: dict) -> None:
        url = step.get("url")
        if url:
            self._last_opened_url = str(url)
            self._open_url(url)

    def _handle_wait_for_url(self, step: dict) -> None:
        url = step.get("url") or self._last_opened_url
        if not url:
            tprint("[EXECUTOR] wait_for_url missing url and no previous open_url")
            return
        timeout_secs = float(step.get("timeout_secs", 15))
        interval_secs = float(step.get("interval_secs", 0.5))
        self._wait_for_url(str(url), timeout_secs=timeout_secs, interval_secs=interval_secs)

    def _handle_open_app(self, step: dict) -> None:
        app = step.get("app")
        if app:
            self._open_app(app)

    def _handle_key_combo(self, step: dict) -> None:
        keys = step.get("keys", [])
        tprint(f"[EXECUTOR] key_combo={keys}")
        self._hotkey(keys)

    def _handle_type_text(self, step: dict) -> None:
        text = step.get("text", "")
        self._type_text(text)

    def _handle_scroll(self, step: dict) -> None:
        direction = step.get("direction", "down")
        amount = int(step.get("amount", 3))
        self._scroll(direction, amount)

    def _handle_mouse_move(self, step: dict) -> None:
        x = int(step.get("x", 0))
        y = int(step.get("y", 0))
        self._mouse_move(x, y)

    def _handle_click(self, step: dict) -> None:
        button = step.get("button", "left")
        clicks = int(step.get("clicks", 1))
        self._click(button, clicks)

    def _open_url(self, url: str) -> None:
        """Open a URL in the default browser, avoiding Python Launcher on macOS."""
        if is_deep_logging():
            deep_log(f"[DEEP][EXECUTOR] _open_url url={url} platform={sys.platform}")
        if sys.platform == "darwin":
            # Use native 'open' command on macOS to avoid Python Launcher issue
            # Use Popen to avoid blocking and DEVNULL to prevent stdio handling
            subprocess.Popen(
                ["open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        if os.name == "nt":
            subprocess.Popen(
                ["cmd", "/c", "start", "", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=True,
            )
            return
        # Linux/Unix: try xdg-open first, fall back to webbrowser
        try:
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            webbrowser.open(url)
    def _open_app(self, app: str) -> None:
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "start", "", app], check=False)
            return
        if sys.platform == "darwin":
            subprocess.run(["open", "-a", app], check=False)
            return
        subprocess.run(["xdg-open", app], check=False)

    def _hotkey(self, keys: list[str]) -> None:
        normalized = self._normalize_keys(keys)
        settings = get_settings()
        if is_deep_logging():
            deep_log(f"[DEEP][EXECUTOR] hotkey keys={normalized}")
        elif settings.get("log_command_debug"):
            tprint(f"[EXECUTOR] hotkey keys={normalized}")

        # On macOS, use AppleScript to avoid Python appearing in dock
        if sys.platform == "darwin":
            self._hotkey_applescript(normalized)
            return

        automation = self._automation()
        if not automation:
            tprint("[EXECUTOR] pyautogui not available; key_combo skipped")
            return
        interval = float(settings.get("command_hotkey_interval_secs", 0.05))
        automation.hotkey(*normalized, interval=interval)

    def _hotkey_applescript(self, keys: list[str]) -> None:
        """Execute hotkey using AppleScript on macOS to avoid dock promotion."""
        if not keys:
            return
        # Map key names to AppleScript key codes
        key_map = {
            "command": "command down",
            "cmd": "command down",
            "control": "control down",
            "ctrl": "control down",
            "alt": "option down",
            "option": "option down",
            "shift": "shift down",
        }
        modifiers = []
        key_to_press = None
        for k in keys:
            k_lower = k.lower()
            if k_lower in key_map:
                modifiers.append(key_map[k_lower])
            else:
                key_to_press = k
        if not key_to_press:
            return
        modifier_str = ", ".join(modifiers) if modifiers else ""
        if modifier_str:
            script = f'tell application "System Events" to keystroke "{key_to_press}" using {{{modifier_str}}}'
        else:
            script = f'tell application "System Events" to keystroke "{key_to_press}"'
        subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _normalize_keys(self, keys: list[str]) -> list[str]:
        if not keys:
            return []
        if sys.platform != "darwin":
            return keys
        mapped = []
        for key in keys:
            if key == "cmd":
                mapped.append("command")
            elif key == "option":
                mapped.append("alt")
            else:
                mapped.append(key)
        return mapped

    def _type_text(self, text: str) -> None:
        if is_deep_logging():
            deep_log(f"[DEEP][EXECUTOR] type_text text={text!r}")
        elif get_settings().get("log_command_debug"):
            tprint(f"[EXECUTOR] type_text text={text!r}")

        # On macOS, use AppleScript to avoid Python appearing in dock
        if sys.platform == "darwin":
            self._type_text_applescript(text)
            return

        automation = self._automation()
        if not automation:
            tprint("[EXECUTOR] pyautogui not available; type_text skipped")
            return
        automation.write(text, interval=0.02)

    def _type_text_applescript(self, text: str) -> None:
        """Type text using AppleScript on macOS to avoid dock promotion."""
        # Escape special characters for AppleScript
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "System Events" to keystroke "{escaped}"'
        subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _scroll(self, direction: str, amount: int) -> None:
        delta = amount * 100
        if is_deep_logging():
            deep_log(f"[DEEP][EXECUTOR] scroll direction={direction} delta={delta}")
        elif get_settings().get("log_command_debug"):
            tprint(f"[EXECUTOR] scroll direction={direction} delta={delta}")

        # On macOS, use AppleScript to avoid Python appearing in dock
        if sys.platform == "darwin":
            self._scroll_applescript(direction, amount)
            return

        automation = self._automation()
        if not automation:
            tprint("[EXECUTOR] pyautogui not available; scroll skipped")
            return
        automation.scroll(delta if direction == "up" else -delta)

    def _scroll_applescript(self, direction: str, amount: int) -> None:
        """Scroll using AppleScript on macOS to avoid dock promotion."""
        # AppleScript scroll: negative for down, positive for up
        scroll_amount = amount if direction == "up" else -amount
        script = f'''
        tell application "System Events"
            repeat {abs(amount)} times
                key code {116 if direction == "up" else 121}
            end repeat
        end tell
        '''
        subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _mouse_move(self, x: int, y: int) -> None:
        automation = self._automation()
        if not automation:
            tprint("[EXECUTOR] pyautogui not available; mouse_move skipped")
            return
        if is_deep_logging():
            deep_log(f"[DEEP][EXECUTOR] pyautogui moveTo x={x} y={y}")
        elif get_settings().get("log_command_debug"):
            tprint(f"[EXECUTOR][pyautogui] moveTo x={x} y={y}")
        automation.moveTo(x, y)

    def _click(self, button: str, clicks: int) -> None:
        automation = self._automation()
        if not automation:
            tprint("[EXECUTOR] pyautogui not available; click skipped")
            return
        if is_deep_logging():
            deep_log(f"[DEEP][EXECUTOR] pyautogui click button={button} clicks={clicks}")
        elif get_settings().get("log_command_debug"):
            tprint(f"[EXECUTOR][pyautogui] click button={button} clicks={clicks}")
        automation.click(button=button, clicks=clicks)

    def _automation(self):
        try:
            import pyautogui
        except Exception:
            return None
        return pyautogui

    def _wait_for_url(self, url: str, *, timeout_secs: float, interval_secs: float) -> None:
        import time
        from urllib import request as urlrequest
        from urllib.error import URLError, HTTPError

        deadline = time.monotonic() + max(0.0, timeout_secs)
        while time.monotonic() < deadline:
            try:
                with urlrequest.urlopen(url, timeout=5) as resp:
                    if 200 <= resp.status < 400:
                        return
            except (URLError, HTTPError):
                pass
            time.sleep(max(0.05, interval_secs))
