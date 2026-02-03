"""macOS-native executor using open and AppleScript."""

from __future__ import annotations

import subprocess
import time

from command_controller.executors.base import BaseExecutor, ExecutionResult
from utils.log_utils import tprint
from utils.settings_store import deep_log, get_settings, is_deep_logging


class MacOSExecutor(BaseExecutor):
    def execute_step(self, step: dict) -> ExecutionResult:
        intent = str(step.get("intent", "")).strip()
        start = time.monotonic()
        target = step.get("target", "os")

        try:
            if intent == "open_url":
                url = str(step.get("url", "")).strip()
                if not url:
                    return self._failed(intent, target, "missing url", start)
                self._open_url(url)
                return self._ok(intent, target, start)

            if intent == "open_app":
                app = str(step.get("app", "")).strip()
                if not app:
                    return self._failed(intent, target, "missing app", start)
                self._open_app(app)
                return self._ok(intent, target, start)

            if intent == "open_file":
                path = str(step.get("path", "")).strip()
                if not path:
                    return self._failed(intent, target, "missing path", start)
                self._open_file(path)
                return self._ok(intent, target, start)

            if intent == "key_combo":
                keys = step.get("keys", [])
                self._hotkey(keys)
                return self._ok(intent, target, start)

            if intent == "type_text":
                text = str(step.get("text", ""))
                self._type_text(text)
                return self._ok(intent, target, start)

            if intent == "wait_for_url":
                return self._unsupported(intent, target, "wait_for_url removed; use target:web", start)

            if intent == "find_ui":
                return self._unsupported(intent, target, "find_ui not implemented", start)

            if intent == "invoke_ui":
                return self._unsupported(intent, target, "invoke_ui not implemented", start)

            if intent == "wait_for_window":
                return self._unsupported(intent, target, "wait_for_window not implemented", start)

            return self._unsupported(intent, target, "unsupported intent", start)
        except Exception as exc:
            return self._failed(intent, target, str(exc), start)

    def _open_url(self, url: str) -> None:
        if is_deep_logging():
            deep_log(f"[DEEP][MAC_EXEC] open_url url={url}")
        subprocess.Popen(
            ["open", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _open_app(self, app: str) -> None:
        if is_deep_logging():
            deep_log(f"[DEEP][MAC_EXEC] open_app app={app}")
        subprocess.Popen(
            ["open", "-a", app],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _open_file(self, path: str) -> None:
        if is_deep_logging():
            deep_log(f"[DEEP][MAC_EXEC] open_file path={path}")
        subprocess.Popen(
            ["open", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _hotkey(self, keys: list[str]) -> None:
        normalized = self._normalize_keys(keys)
        settings = get_settings()
        if is_deep_logging():
            deep_log(f"[DEEP][MAC_EXEC] hotkey keys={normalized}")
        elif settings.get("log_command_debug"):
            tprint(f"[MAC_EXEC] hotkey keys={normalized}")
        if not normalized:
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
        for key in normalized:
            key_lower = str(key).lower()
            if key_lower in key_map:
                modifiers.append(key_map[key_lower])
            else:
                key_to_press = key_lower
        if not key_to_press:
            return
        modifier_str = ", ".join(modifiers) if modifiers else ""
        if modifier_str:
            script = (
                f'tell application "System Events" to keystroke '
                f'"{key_to_press}" using {{{modifier_str}}}'
            )
        else:
            script = f'tell application "System Events" to keystroke "{key_to_press}"'
        subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _type_text(self, text: str) -> None:
        if is_deep_logging():
            deep_log(f"[DEEP][MAC_EXEC] type_text text={text!r}")
        elif get_settings().get("log_command_debug"):
            tprint(f"[MAC_EXEC] type_text text={text!r}")
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "System Events" to keystroke "{escaped}"'
        subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _normalize_keys(self, keys: list[str]) -> list[str]:
        if not keys:
            return []
        mapped = []
        for key in keys:
            if key == "cmd":
                mapped.append("command")
            elif key == "option":
                mapped.append("alt")
            else:
                mapped.append(key)
        return mapped

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
