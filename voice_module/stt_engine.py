"""Speech-to-text engine with OpenAI Realtime streaming support."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from typing import AsyncIterable, Iterable

import websockets
from voice_module.stt_whisperlive import WhisperLiveClient
from voice_module.stt_whisper_local import WhisperLocalEngine


class SpeechToTextEngine:
    """Streams PCM audio to OpenAI Realtime for low-latency transcription."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        default_sample_rate: int = 24000,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv(
            "OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview"
        )
        self.transcription_model = os.getenv(
            "OPENAI_TRANSCRIPTION_MODEL", "whisper-1"
        )
        self.transcription_language = os.getenv("OPENAI_TRANSCRIPTION_LANGUAGE", "en")
        self.project_id = os.getenv("OPENAI_PROJECT_ID")
        self.base_url = base_url or os.getenv(
            "OPENAI_REALTIME_URL", "wss://api.openai.com/v1/realtime"
        )
        self.default_sample_rate = default_sample_rate
        self.debug = os.getenv("OPENAI_REALTIME_DEBUG", "0").lower() in {"1", "true", "yes", "on"}
        self.last_usage: dict | None = None
        self.last_response_id: str | None = None
        self.provider = (os.getenv("STT_PROVIDER") or "openai-realtime").lower()
        self._whisper_local: WhisperLocalEngine | None = None

    def transcribe_text(
        self,
        text: str
    ) -> str:
        """Fallback helper for simple text input (non-audio)."""
        return text.lower()

    async def transcribe_stream(
        self,
        audio_stream: AsyncIterable[bytes | str] | Iterable[bytes | str],
        sample_rate: int | None = None,
        timeout_seconds: float = 30.0,
    ) -> str:
        """Send an audio stream to OpenAI Realtime and return the transcript."""
        if self.provider == "whisperlive":
            return await self._transcribe_whisperlive(audio_stream)
        if self.provider == "whisper-local":
            return await self._transcribe_whisper_local(audio_stream)

        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for Realtime STT")

        # Reset usage tracking for this call.
        self.last_usage = None
        self.last_response_id = None

        rate = sample_rate or self.default_sample_rate
        if rate <= 0:
            raise ValueError("sample_rate must be positive")

        ws_url = f"{self.base_url}?model={self.model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        if self.project_id:
            headers["OpenAI-Project"] = self.project_id

        connect_kwargs = {"max_size": None, "compression": None}

        try:
            websocket_cm = websockets.connect(
                ws_url, extra_headers=headers, **connect_kwargs
            )
        except TypeError as exc:
            if "extra_headers" in str(exc):
                raise RuntimeError(
                    "Your 'websockets' package is too old for auth headers. "
                    "Install websockets>=12 (e.g., pip install 'websockets>=12,<13')."
                ) from exc
            raise

        async with websocket_cm as websocket:
            await self._send_session_update(websocket, rate)
            async for chunk in _to_async_iter(audio_stream):
                if chunk is None:
                    continue
                audio_b64 = (
                    chunk
                    if isinstance(chunk, str)
                    else base64.b64encode(chunk).decode("ascii")
                )
                await websocket.send(
                    json.dumps(
                        {
                            "type": "input_audio_buffer.append",
                            "audio": audio_b64,
                        }
                    )
                )
            await websocket.send(json.dumps({"type": "input_audio_buffer.commit"}))
            await websocket.send(json.dumps({"type": "response.create"}))
            transcript = await self._collect_transcript(websocket, timeout_seconds)
            return transcript

    async def _send_session_update(
        self, websocket: websockets.WebSocketClientProtocol, sample_rate: int
    ) -> None:
        """Configure the realtime session for audio-only text output."""
        await websocket.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "input_audio_format": "pcm16",
                        "input_audio_transcription": {
                            "model": self.transcription_model,
                            "language": self.transcription_language,
                        },
                        "modalities": ["text"],
                    },
                }
            )
        )

    async def _collect_transcript(
        self, websocket: websockets.WebSocketClientProtocol, timeout_seconds: float
    ) -> str:
        """Receive events until the response completes and return the transcript."""
        parts: list[str] = []
        done_events = {"response.completed", "response.done"}
        text_delta_events = {"response.output_text.delta", "response.text.delta", "response.delta"}
        transcription_delta_events = {
            "conversation.item.input_audio_transcription.delta",
        }
        transcription_done_events = {
            "conversation.item.input_audio_transcription.completed",
        }

        while True:
            raw = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
            event = json.loads(raw)
            event_type = event.get("type")

            if self.debug:
                print(f"[VOICE][DEBUG] event: {event_type} payload={event}")

            if event_type and "error" in event_type:
                message = event.get("message") or event.get("error", "")
                raise RuntimeError(self._format_realtime_error(event_type, message, event))

            if event_type in text_delta_events:
                delta = event.get("delta") or event.get("text") or ""
                parts.append(delta)

            if event_type in transcription_delta_events:
                delta = event.get("delta") or ""
                parts.append(delta)

            if event_type in transcription_done_events:
                final_text = event.get("transcript") or ""
                if final_text:
                    parts.append(final_text)

            if event_type in {"response.output_text.done", "response.text.done"}:
                # Some responses send a final text field; capture it if present.
                final_text = event.get("text")
                if final_text:
                    parts.append(final_text)

            if event_type in done_events:
                response_obj = event.get("response") or {}
                self.last_response_id = response_obj.get("id")
                usage = response_obj.get("usage")
                if usage:
                    self.last_usage = usage
                break

        return "".join(parts).strip()

    def _format_realtime_error(self, event_type: str, message: str, payload: dict) -> str:
        """Improve visibility into billing/access errors."""
        msg_lower = (message or "").lower()
        hints: list[str] = []
        if "insufficient" in msg_lower or "quota" in msg_lower:
            hints.append("Possible cause: insufficient credits or billing not enabled.")
        if "model_not_found" in msg_lower or "does not exist" in msg_lower:
            hints.append("Possible cause: model string not available to this account.")
        hint_txt = f" Hints: {' '.join(hints)}" if hints else ""
        return f"Realtime STT error: {event_type} {message} payload={payload}.{hint_txt}"

    def format_usage(self) -> str | None:
        """Format the last usage info for logging."""
        if not self.last_usage:
            return None
        u = self.last_usage
        total = u.get("total_tokens")
        input_tokens = u.get("input_tokens")
        output_tokens = u.get("output_tokens")
        return f"tokens total={total} input={input_tokens} output={output_tokens} (remaining not provided by API)"

    async def _transcribe_whisperlive(
        self, audio_stream: AsyncIterable[bytes] | Iterable[bytes]
    ) -> str:
        """Route audio to a local WhisperLive server."""
        client = WhisperLiveClient()
        return await client.transcribe_stream(audio_stream)

    async def _transcribe_whisper_local(
        self, audio_stream: AsyncIterable[bytes | str] | Iterable[bytes | str]
    ) -> str:
        """Route audio to local faster-whisper (no network)."""
        if self._whisper_local is None:
            self._whisper_local = WhisperLocalEngine(language=self.transcription_language)
        return await self._whisper_local.transcribe_stream(audio_stream)


async def _to_async_iter(stream: AsyncIterable[bytes | str] | Iterable[bytes | str]) -> AsyncIterable[bytes | str]:
    """Normalize sync or async iterables to an async iterator of audio chunks."""
    if hasattr(stream, "__aiter__"):
        async for item in stream:  # type: ignore[operator]
            yield item
    else:
        for item in stream:
            yield item
