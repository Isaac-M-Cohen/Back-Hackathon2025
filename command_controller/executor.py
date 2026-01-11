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
        self.hotkey_interval = float(settings.get("command_hotkey_interval_secs", 0.05))

    def execute(self, action: str, payload: dict) -> None:
        print(f"[EXECUTOR] Performing action='{action}' payload={payload}")

    def execute_steps(self, steps: list[dict]) -> None:
        for step in steps:
            self.execute_step(step)

    def execute_step(self, step: dict) -> None:
        intent = step.get("intent")
        if intent == "open_url":
            url = step.get("url")
            if url:
                webbrowser.open(url)
            return
        if intent == "open_app":
            app = step.get("app")
            if app:
                self._open_app(app)
            return
        if intent == "key_combo":
            keys = step.get("keys", [])
            print(f"[EXECUTOR] key_combo={keys}")
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
        print(f"[EXECUTOR] Unknown intent '{intent}'")

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
        automation.hotkey(*normalized, interval=self.hotkey_interval)

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
