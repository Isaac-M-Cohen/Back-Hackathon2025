"""Fallback executor using PyAutoGUI and OS helpers."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser

from command_controller.executors.base import BaseExecutor, ExecutionResult
from utils.log_utils import tprint
from utils.settings_store import deep_log, get_settings, is_deep_logging


class PyAutoGUIExecutor(BaseExecutor):
    def __init__(self) -> None:
        self._last_opened_url: str | None = None

    def execute_step(self, step: dict) -> ExecutionResult:
        intent = step.get("intent")
        start = time.monotonic()
        target = step.get("target", "os")
        try:
            if intent == "open_url":
                url = step.get("url")
                if not url:
                    return self._failed(intent, target, "missing url", start)
                self._last_opened_url = str(url)
                self._open_url(url)
                return self._ok(intent, target, start)
            if intent == "wait_for_url":
                url = step.get("url") or self._last_opened_url
                if not url:
                    return self._failed(intent, target, "missing url", start)
                timeout_secs = float(step.get("timeout_secs", 15))
                interval_secs = float(step.get("interval_secs", 0.5))
                self._wait_for_url(str(url), timeout_secs=timeout_secs, interval_secs=interval_secs)
                return self._ok(intent, target, start)
            if intent == "open_app":
                app = step.get("app")
                if not app:
                    return self._failed(intent, target, "missing app", start)
                self._open_app(app)
                return self._ok(intent, target, start)
            if intent == "open_file":
                path = step.get("path")
                if not path:
                    return self._failed(intent, target, "missing path", start)
                self._open_file(path)
                return self._ok(intent, target, start)
            if intent == "key_combo":
                keys = step.get("keys", [])
                tprint(f"[EXECUTOR] key_combo={keys}")
                self._hotkey(keys)
                return self._ok(intent, target, start)
            if intent == "type_text":
                text = step.get("text", "")
                self._type_text(text)
                return self._ok(intent, target, start)
            if intent == "scroll":
                direction = step.get("direction", "down")
                amount = int(step.get("amount", 3))
                self._scroll(direction, amount)
                return self._ok(intent, target, start)
            if intent == "mouse_move":
                x = int(step.get("x", 0))
                y = int(step.get("y", 0))
                self._mouse_move(x, y)
                return self._ok(intent, target, start)
            if intent == "click":
                button = step.get("button", "left")
                clicks = int(step.get("clicks", 1))
                self._click(button, clicks)
                return self._ok(intent, target, start)
            if intent in {"find_ui", "invoke_ui", "wait_for_window"}:
                return self._unsupported(intent, target, "not supported by pyautogui", start)
            return self._unsupported(intent, target, "unsupported intent", start)
        except Exception as exc:
            return self._failed(intent or "unknown", target, str(exc), start)

    def _open_url(self, url: str) -> None:
        if is_deep_logging():
            deep_log(f"[DEEP][EXECUTOR] _open_url url={url} platform={sys.platform}")
        if sys.platform == "darwin":
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

    def _open_file(self, path: str) -> None:
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "start", "", path], check=False)
            return
        if sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
            return
        subprocess.run(["xdg-open", path], check=False)

    def _hotkey(self, keys: list[str]) -> None:
        normalized = self._normalize_keys(keys)
        settings = get_settings()
        if is_deep_logging():
            deep_log(f"[DEEP][EXECUTOR] hotkey keys={normalized}")
        elif settings.get("log_command_debug"):
            tprint(f"[EXECUTOR] hotkey keys={normalized}")

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
        if not keys:
            return
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

        if sys.platform == "darwin":
            self._type_text_applescript(text)
            return

        automation = self._automation()
        if not automation:
            tprint("[EXECUTOR] pyautogui not available; type_text skipped")
            return
        automation.write(text, interval=0.02)

    def _type_text_applescript(self, text: str) -> None:
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

        if sys.platform == "darwin":
            self._scroll_applescript(direction, amount)
            return

        automation = self._automation()
        if not automation:
            tprint("[EXECUTOR] pyautogui not available; scroll skipped")
            return
        automation.scroll(delta if direction == "up" else -delta)

    def _scroll_applescript(self, direction: str, amount: int) -> None:
        scroll_amount = amount if direction == "up" else -amount
        script = f"""
        tell application "System Events"
            repeat {abs(amount)} times
                key code {116 if direction == "up" else 121}
            end repeat
        end tell
        """
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
        import time as time_mod
        from urllib import request as urlrequest
        from urllib.error import URLError, HTTPError

        deadline = time_mod.monotonic() + max(0.0, timeout_secs)
        while time_mod.monotonic() < deadline:
            try:
                with urlrequest.urlopen(url, timeout=5) as resp:
                    if 200 <= resp.status < 400:
                        return
            except (URLError, HTTPError):
                pass
            time_mod.sleep(max(0.05, interval_secs))

    def _ok(self, intent: str, target: str, start: float) -> ExecutionResult:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return ExecutionResult(intent=intent, status="ok", target=target, elapsed_ms=elapsed_ms)

    def _failed(self, intent: str, target: str, reason: str, start: float) -> ExecutionResult:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return ExecutionResult(
            intent=intent,
            status="failed",
            target=target,
            details={"reason": reason},
            elapsed_ms=elapsed_ms,
        )

    def _unsupported(self, intent: str, target: str, reason: str, start: float) -> ExecutionResult:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return ExecutionResult(
            intent=intent,
            status="unsupported",
            target=target,
            details={"reason": reason},
            elapsed_ms=elapsed_ms,
        )

