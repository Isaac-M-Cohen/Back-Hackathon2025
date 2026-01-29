"""Intent schema and validation for command execution."""

from __future__ import annotations

from typing import Any


class WebExecutionError(RuntimeError):
    """Structured error from a web execution step."""

    def __init__(
        self, code: str, message: str, screenshot_path: str | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.screenshot_path = screenshot_path


ALLOWED_INTENTS = {
    "open_url",
    "wait_for_url",
    "open_app",
    "open_file",
    "key_combo",
    "type_text",
    "scroll",
    "mouse_move",
    "click",
    "web_send_message",
    "find_ui",
    "invoke_ui",
    "wait_for_window",
}

KEY_ALIASES = {
    "cmd": "command",
    "command": "command",
    "ctrl": "control",
    "control": "control",
    "opt": "alt",
    "option": "alt",
    "alt": "alt",
    "shift": "shift",
    "enter": "enter",
    "return": "enter",
    "esc": "esc",
    "escape": "esc",
}


def normalize_steps(payload: Any) -> list[dict]:
    """Return a normalized list of intent steps from a parsed payload."""
    if isinstance(payload, list):
        return [step for step in payload if isinstance(step, dict)]
    if isinstance(payload, dict):
        steps = payload.get("steps")
        if isinstance(steps, list):
            return [step for step in steps if isinstance(step, dict)]
    return []


def validate_step(step: dict) -> dict:
    """Validate an intent step and return a sanitized copy."""
    intent = str(step.get("intent", "")).strip()
    if intent not in ALLOWED_INTENTS:
        raise ValueError(f"Unsupported intent '{intent}'")

    cleaned: dict[str, Any] = {"intent": intent}
    target = step.get("target")
    if isinstance(target, str) and target:
        cleaned["target"] = target
    if intent == "open_url":
        url = str(step.get("url", "")).strip()
        if not url:
            raise ValueError("open_url requires 'url'")
        cleaned["url"] = url
        return cleaned

    if intent == "wait_for_url":
        url = str(step.get("url", "")).strip()
        timeout = step.get("timeout_secs", 15)
        interval = step.get("interval_secs", 0.5)
        cleaned["url"] = url
        try:
            cleaned["timeout_secs"] = float(timeout)
        except (TypeError, ValueError):
            raise ValueError("wait_for_url requires numeric 'timeout_secs'")
        try:
            cleaned["interval_secs"] = float(interval)
        except (TypeError, ValueError):
            raise ValueError("wait_for_url requires numeric 'interval_secs'")
        return cleaned

    if intent == "open_app":
        app = str(step.get("app", "")).strip()
        if not app:
            raise ValueError("open_app requires 'app'")
        cleaned["app"] = app
        return cleaned

    if intent == "open_file":
        path = str(step.get("path", "")).strip()
        if not path:
            raise ValueError("open_file requires 'path'")
        cleaned["path"] = path
        return cleaned

    if intent == "key_combo":
        keys = step.get("keys") or []
        if isinstance(keys, str):
            keys = [item.strip() for item in keys.split("+") if item.strip()]
        if not isinstance(keys, list) or not keys:
            raise ValueError("key_combo requires non-empty 'keys'")
        cleaned_keys = []
        for key in keys:
            key_str = str(key).strip().lower()
            if not key_str:
                continue
            cleaned_keys.append(KEY_ALIASES.get(key_str, key_str))
        if not cleaned_keys:
            raise ValueError("key_combo requires non-empty 'keys'")
        cleaned["keys"] = cleaned_keys
        return cleaned

    if intent == "type_text":
        text = str(step.get("text", ""))
        if text == "":
            raise ValueError("type_text requires 'text'")
        cleaned["text"] = text
        return cleaned

    if intent == "scroll":
        direction = str(step.get("direction", "down")).strip().lower()
        if direction not in {"up", "down"}:
            raise ValueError("scroll direction must be 'up' or 'down'")
        amount = step.get("amount", 3)
        try:
            amount_int = int(amount)
        except (TypeError, ValueError):
            raise ValueError("scroll requires integer 'amount'")
        cleaned["direction"] = direction
        cleaned["amount"] = max(1, amount_int)
        return cleaned

    if intent == "mouse_move":
        x = step.get("x")
        y = step.get("y")
        if x is None or y is None:
            raise ValueError("mouse_move requires 'x' and 'y' coordinates")
        try:
            x_int = int(x)
        except (TypeError, ValueError):
            raise ValueError("mouse_move requires integer 'x'")
        try:
            y_int = int(y)
        except (TypeError, ValueError):
            raise ValueError("mouse_move requires integer 'y'")
        cleaned["x"] = x_int
        cleaned["y"] = y_int
        return cleaned

    if intent == "click":
        button = str(step.get("button", "left")).strip().lower()
        if button not in {"left", "right", "middle"}:
            raise ValueError("click button must be 'left', 'right', or 'middle'")
        clicks = step.get("clicks", 1)
        try:
            clicks_int = int(clicks)
        except (TypeError, ValueError):
            raise ValueError("click requires integer 'clicks'")
        cleaned["button"] = button
        cleaned["clicks"] = max(1, clicks_int)
        return cleaned

    if intent == "web_send_message":
        contact = str(step.get("contact", "")).strip()
        message = str(step.get("message", "")).strip()
        if not contact:
            raise ValueError("web_send_message requires 'contact'")
        if not message:
            raise ValueError("web_send_message requires 'message'")
        cleaned["contact"] = contact
        cleaned["message"] = message
        cleaned["target"] = "web"
        return cleaned

    if intent == "find_ui":
        selector = step.get("selector")
        if not isinstance(selector, dict):
            raise ValueError("find_ui requires 'selector' object")
        cleaned["selector"] = _clean_selector(selector)
        return cleaned

    if intent == "invoke_ui":
        element_id = step.get("element_id")
        if element_id is not None:
            cleaned["element_id"] = str(element_id).strip()
            return cleaned
        selector = step.get("selector")
        if not isinstance(selector, dict):
            raise ValueError("invoke_ui requires 'selector' object or 'element_id'")
        cleaned["selector"] = _clean_selector(selector)
        return cleaned

    if intent == "wait_for_window":
        title = str(step.get("window_title", "")).strip()
        if not title:
            raise ValueError("wait_for_window requires 'window_title'")
        app = str(step.get("app", "")).strip()
        timeout = step.get("timeout_secs", 10)
        cleaned["window_title"] = title
        if app:
            cleaned["app"] = app
        try:
            cleaned["timeout_secs"] = float(timeout)
        except (TypeError, ValueError):
            raise ValueError("wait_for_window requires numeric 'timeout_secs'")
        return cleaned

    raise ValueError(f"Unsupported intent '{intent}'")


def validate_steps(steps: list[dict]) -> list[dict]:
    """Validate a list of steps and return sanitized copies."""
    return [validate_step(step) for step in steps]


def _clean_selector(selector: dict) -> dict:
    allowed = {"app", "window_title", "role", "name", "contains", "automation_id"}
    cleaned: dict[str, Any] = {}
    for key in allowed:
        if key not in selector:
            continue
        value = selector[key]
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        cleaned[key] = value
    if not cleaned:
        raise ValueError("selector requires at least one field")
    return cleaned
