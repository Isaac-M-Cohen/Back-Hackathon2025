"""Local LLM client for intent extraction."""

from __future__ import annotations

import json
import os
import re
from typing import Iterable
from urllib import request
from urllib.error import URLError

from utils.file_utils import load_json


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
            '    {"intent":"open_url","url":"https://..."},\n'
            '    {"intent":"wait_for_url","url":"https://...","timeout_secs":15,"interval_secs":0.5},\n'
            '    {"intent":"open_app","app":"App Name"},\n'
            '    {"intent":"key_combo","keys":["cmd","l"]},\n'
            '    {"intent":"type_text","text":"hello"},\n'
            '    {"intent":"scroll","direction":"down","amount":3}\n'
            "  ]\n"
            "}\n"
            "Rules:\n"
            "- Only output JSON. No markdown, no commentary.\n"
            "- Use the smallest number of steps.\n"
            "- If the request is ambiguous, return an empty steps list.\n"
            "- For copy/paste/cut/undo/redo/select all, use key_combo with cmd on macOS or ctrl on Windows.\n"
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
