"""Executes mapped system actions."""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser

from utils.file_utils import load_json


class Executor:
    def __init__(self) -> None:
        settings = load_json("config/app_settings.json")
        self.log_debug = bool(settings.get("log_command_debug", False))
        self._last_opened_url: str | None = None
        self._intent_handlers = {
            "open_url": self._handle_open_url,
            "wait_for_url": self._handle_wait_for_url,
            "open_app": self._handle_open_app,
            "key_combo": self._handle_key_combo,
            "type_text": self._handle_type_text,
            "scroll": self._handle_scroll,
        }

    def execute(self, action: str, payload: dict) -> None:
        print(f"[EXECUTOR] Performing action='{action}' payload={payload}")

    def execute_steps(self, steps: list[dict]) -> None:
        for step in steps:
            self.execute_step(step)

    def execute_step(self, step: dict) -> None:
        intent = step.get("intent")
        handler = self._intent_handlers.get(intent)
        if handler:
            handler(step)
            return
        print(f"[EXECUTOR] Unknown intent '{intent}'")

    def _handle_open_url(self, step: dict) -> None:
        url = step.get("url")
        if url:
            self._last_opened_url = str(url)
            webbrowser.open(url)

    def _handle_wait_for_url(self, step: dict) -> None:
        url = step.get("url") or self._last_opened_url
        if not url:
            print("[EXECUTOR] wait_for_url missing url and no previous open_url")
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
        print(f"[EXECUTOR] key_combo={keys}")
        self._hotkey(keys)

    def _handle_type_text(self, step: dict) -> None:
        text = step.get("text", "")
        self._type_text(text)

    def _handle_scroll(self, step: dict) -> None:
        direction = step.get("direction", "down")
        amount = int(step.get("amount", 3))
        self._scroll(direction, amount)

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
            print("[EXECUTOR] pyautogui not available; key_combo skipped")
            return
        normalized = self._normalize_keys(keys)
        if self.log_debug:
            print(f"[EXECUTOR][pyautogui] hotkey args={normalized}")
        automation.hotkey(*normalized)

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
            print("[EXECUTOR] pyautogui not available; type_text skipped")
            return
        if self.log_debug:
            print(f"[EXECUTOR][pyautogui] write text={text!r}")
        automation.write(text, interval=0.02)

    def _scroll(self, direction: str, amount: int) -> None:
        automation = self._automation()
        if not automation:
            print("[EXECUTOR] pyautogui not available; scroll skipped")
            return
        delta = amount * 100
        if self.log_debug:
            print(f"[EXECUTOR][pyautogui] scroll delta={delta}")
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
