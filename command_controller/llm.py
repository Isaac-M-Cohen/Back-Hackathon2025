"""Local LLM client for intent extraction."""

from __future__ import annotations

import json
import os
import re
from typing import Iterable
from urllib import request
from urllib.error import URLError

from utils.file_utils import load_json
from utils.log_utils import tprint
from utils.settings_store import deep_log, get_settings, is_deep_logging


class LocalLLMError(RuntimeError):
    pass


class LocalLLMInterpreter:
    def __init__(self, settings_path: str = "config/command_settings.json") -> None:
        settings = load_json(settings_path)
        self.base_url = os.getenv("EASY_OLLAMA_URL", settings.get("ollama_url", "http://127.0.0.1:11434"))
        self.model = os.getenv("EASY_OLLAMA_MODEL", settings.get("ollama_model", "llama3.1:8b"))
        self.timeout_secs = float(settings.get("request_timeout_secs", 30))

    def interpret(
        self,
        text: str,
        context: dict | None = None,
        supported_intents: Iterable[str] | None = None,
    ) -> dict:
        prompt = self._build_prompt(text, context or {}, supported_intents)
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2},
            }
        ).encode("utf-8")
        req = request.Request(
            f"{self.base_url.rstrip('/')}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with request.urlopen(req, timeout=self.timeout_secs) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except URLError as exc:
            raise LocalLLMError(f"Local LLM unavailable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LocalLLMError(f"Invalid LLM response: {exc}") from exc

        output = data.get("response", "")
        if is_deep_logging():
            deep_log(f"[DEEP][LLM] raw_response={output}")
        elif get_settings().get("log_command_debug"):
            tprint(f"[LLM] raw_response={output}")
        parsed = self._extract_json(output)
        if parsed is None:
            raise LocalLLMError("LLM did not return valid JSON")
        return parsed

    def _build_prompt(
        self,
        text: str,
        context: dict,
        supported_intents: Iterable[str] | None,
    ) -> str:
        context_json = json.dumps(context, ensure_ascii=True)
        intent_list = ", ".join(sorted(supported_intents or []))
        intent_line = f"Supported intents: {intent_list}\n" if intent_list else ""
        return (
            "You are a command intent parser. Convert the user request into JSON only. "
            f"{intent_line}"
            "Use this schema:\n"
            "{\n"
            '  "steps": [\n'
            '    {"intent":"open_url","url":"https://...","target":"web"},\n'
            '    {"intent":"type_text","text":"hello","target":"web","selector":"input[name=q]"},\n'
            '    {"intent":"key_combo","keys":["enter"],"target":"web"},\n'
            '    {"intent":"click","button":"left","clicks":1,"target":"web","selector":"button.submit"},\n'
            '    {"intent":"scroll","direction":"down","amount":3},\n'
            '    {"intent":"open_url","url":"https://..."},\n'
            '    {"intent":"wait_for_url","url":"https://...","timeout_secs":15,"interval_secs":0.5},\n'
            '    {"intent":"open_app","app":"App Name"},\n'
            '    {"intent":"open_file","path":"/path/to/file"},\n'
            '    {"intent":"key_combo","keys":["cmd","l"]},\n'
            '    {"intent":"type_text","text":"hello"},\n'
            '    {"intent":"scroll","direction":"down","amount":3},\n'
            '    {"intent":"mouse_move","x":100,"y":200},\n'
            '    {"intent":"click","button":"left","clicks":1},\n'
            '    {"intent":"find_ui","selector":{"app":"App","window_title":"Title","role":"button","name":"OK","contains":true}},\n'
            '    {"intent":"invoke_ui","selector":{"app":"App","name":"OK"}},\n'
            '    {"intent":"wait_for_window","window_title":"Title","app":"App","timeout_secs":10},\n'
            '    {"intent":"web_send_message","contact":"John Doe","message":"Hello!"}\n'
            "  ]\n"
            "}\n"
            "Rules:\n"
            "- Only output JSON. No markdown, no commentary.\n"
            "- Use the minimum number of steps that reliably complete the task.\n"
            "- If the request is ambiguous, return an empty steps list.\n"
            "- For copy/paste/cut/undo/redo/select all, use key_combo with cmd on macOS or ctrl on Windows.\n"
            "- Use mouse_move and click for multi-step workflows that require precise cursor positioning.\n"
            "- Prefer find_ui/invoke_ui over pixel-based clicks when possible.\n"
            "- For sending messages on WhatsApp, use web_send_message with contact (display name) and message. Do NOT use pixel-level clicks or type_text for WhatsApp.\n"
            "- web_send_message is a high-level intent. Never decompose it into open_url + type_text + click.\n"
            "- When opening a URL for in-browser interaction (typing, clicking, etc.), set \"target\":\"web\" on the open_url step. Subsequent type_text, key_combo, click, and scroll steps will automatically run inside the browser.\n"
            "- When target is \"web\", prefer using a CSS \"selector\" on type_text and click to target specific elements (e.g. \"input[name=search_query]\").\n"
            "- Do NOT emit wait_for_url steps when using target:\"web\" — page-load waiting is handled automatically.\n"
            f"Context: {context_json}\n"
            f"Request: {text}"
        )

    def _extract_json(self, text: str) -> dict | list | None:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return None
