"""WhisperLive client for local, low-latency transcription."""

from __future__ import annotations

import asyncio
import base64
import os
from typing import AsyncIterable, Iterable

import aiohttp


class WhisperLiveClient:
    """Streams audio chunks to a WhisperLive server and returns the transcript."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        language: str | None = None,
        chunk_ms: int | None = None,
    ) -> None:
        self.base_url = base_url or os.getenv("WHISPERLIVE_URL", "http://localhost:9090")
        self.model = model or os.getenv("WHISPERLIVE_MODEL", "small")
        self.language = language or os.getenv("WHISPERLIVE_LANGUAGE", "en")
        self.chunk_ms = chunk_ms or int(os.getenv("WHISPERLIVE_CHUNK_MS", "500"))

    async def transcribe_stream(
        self, audio_stream: AsyncIterable[bytes] | Iterable[bytes]
    ) -> str:
        """Send PCM16 audio chunks to WhisperLive and return the combined transcript."""
        # WhisperLive expects base64 PCM chunks via SSE or HTTP. We'll POST chunks and collect interim text.
        # Endpoint: POST /inference with fields: model, language, chunk_ms, audio (base64)
        url = f"{self.base_url}/inference"
        transcript_parts: list[str] = []
        async with aiohttp.ClientSession() as session:
            async for chunk in _to_async_iter(audio_stream):
                if not chunk:
                    continue
                audio_b64 = base64.b64encode(chunk).decode("ascii")
                payload = {
                    "model": self.model,
                    "language": self.language,
                    "chunk_ms": self.chunk_ms,
                    "audio": audio_b64,
                }
                async with session.post(url, json=payload, timeout=30) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"WhisperLive error {resp.status}: {text}")
                    data = await resp.json()
                    if text := data.get("text") or data.get("transcript"):
                        transcript_parts.append(text)
        return " ".join(tp.strip() for tp in transcript_parts if tp).strip()


async def _to_async_iter(stream: AsyncIterable[bytes] | Iterable[bytes]):
    if hasattr(stream, "__aiter__"):
        async for item in stream:  # type: ignore[operator]
            yield item
    else:
        for item in stream:
            yield item
