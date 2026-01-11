"""Intent schema and validation for command execution."""

from __future__ import annotations

from typing import Any

ALLOWED_INTENTS = {
    "open_url",
    "wait_for_url",
    "open_app",
    "key_combo",
    "type_text",
    "scroll",
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

    raise ValueError(f"Unsupported intent '{intent}'")


def validate_steps(steps: list[dict]) -> list[dict]:
    """Validate a list of steps and return sanitized copies."""
    return [validate_step(step) for step in steps]
