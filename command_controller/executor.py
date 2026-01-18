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

    def execute(self, action: str, payload: dict) -> None:
        tprint(f"[EXECUTOR] Performing action='{action}' payload={payload}")

    def execute_steps(self, steps: list[dict]) -> None:
        for step in steps:
            self.execute_step(step)

    def execute_step(self, step: dict) -> None:
        intent = step.get("intent")
        if intent == "open_url":
            url = step.get("url")
            if url:
                self._last_opened_url = str(url)
                webbrowser.open(url)
            return
        if intent == "wait_for_url":
            url = step.get("url") or self._last_opened_url
            if not url:
                tprint("[EXECUTOR] wait_for_url missing url and no previous open_url")
                return
            timeout_secs = float(step.get("timeout_secs", 15))
            interval_secs = float(step.get("interval_secs", 0.5))
            self._wait_for_url(str(url), timeout_secs=timeout_secs, interval_secs=interval_secs)
            return
        if intent == "open_app":
            app = step.get("app")
            if app:
                self._open_app(app)
            return
        if intent == "key_combo":
            keys = step.get("keys", [])
            tprint(f"[EXECUTOR] key_combo={keys}")
            self._hotkey(keys)
            return
        if intent == "type_text":
            text = step.get("text", "")
            self._type_text(text)
            return
        if intent == "scroll":
            direction = step.get("direction", "down")
            amount = int(step.get("amount", 3))
            self._scroll(direction, amount)
            return
        tprint(f"[EXECUTOR] Unknown intent '{intent}'")

    def _open_app(self, app: str) -> None:
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "start", "", app], check=False)
            return
        if sys.platform == "darwin":
            subprocess.run(["open", "-a", app], check=False)
            return
        subprocess.run(["xdg-open", app], check=False)

    def _hotkey(self, keys: list[str]) -> None:
        automation = self._automation()
        if not automation:
            tprint("[EXECUTOR] pyautogui not available; key_combo skipped")
            return
        normalized = self._normalize_keys(keys)
        settings = get_settings()
        if is_deep_logging():
            deep_log(f"[DEEP][EXECUTOR] pyautogui hotkey args={normalized}")
        elif settings.get("log_command_debug"):
            tprint(f"[EXECUTOR][pyautogui] hotkey args={normalized}")
        interval = float(settings.get("command_hotkey_interval_secs", 0.05))
        automation.hotkey(*normalized, interval=interval)

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
        automation = self._automation()
        if not automation:
            tprint("[EXECUTOR] pyautogui not available; type_text skipped")
            return
        if is_deep_logging():
            deep_log(f"[DEEP][EXECUTOR] pyautogui write text={text!r}")
        elif get_settings().get("log_command_debug"):
            tprint(f"[EXECUTOR][pyautogui] write text={text!r}")
        automation.write(text, interval=0.02)

    def _scroll(self, direction: str, amount: int) -> None:
        automation = self._automation()
        if not automation:
            tprint("[EXECUTOR] pyautogui not available; scroll skipped")
            return
        delta = amount * 100
        if is_deep_logging():
            deep_log(f"[DEEP][EXECUTOR] pyautogui scroll delta={delta}")
        elif get_settings().get("log_command_debug"):
            tprint(f"[EXECUTOR][pyautogui] scroll delta={delta}")
        automation.scroll(delta if direction == "up" else -delta)

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
