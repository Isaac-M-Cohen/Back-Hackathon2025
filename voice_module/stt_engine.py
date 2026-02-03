"""Speech-to-text engine with local-only Whisper support."""

from __future__ import annotations

import os
from typing import AsyncIterable, Iterable

from voice_module.stt_whisper_local import WhisperLocalEngine


class SpeechToTextEngine:
    """Runs local Whisper transcription only."""

    def __init__(
        self,
        default_sample_rate: int = 24000,
    ) -> None:
        self.transcription_language = os.getenv("LOCAL_WHISPER_LANGUAGE", "en")
        self.default_sample_rate = default_sample_rate
        self.provider = (os.getenv("STT_PROVIDER") or "whisper-local").lower()
        self._whisper_local: WhisperLocalEngine | None = None

    def transcribe_text(self, text: str) -> str:
        """Fallback helper for simple text input (non-audio)."""
        return text.lower()

    async def transcribe_stream(
        self,
        audio_stream: AsyncIterable[bytes | str] | Iterable[bytes | str],
        sample_rate: int | None = None,
        timeout_seconds: float = 30.0,
    ) -> str:
        """Run local Whisper on an audio stream and return the transcript."""
        _ = sample_rate
        _ = timeout_seconds
        if self.provider != "whisper-local":
            raise RuntimeError(
                f"Unsupported STT_PROVIDER '{self.provider}'. Only 'whisper-local' is supported."
            )
        return await self._transcribe_whisper_local(audio_stream)

    async def _transcribe_whisper_local(
        self, audio_stream: AsyncIterable[bytes | str] | Iterable[bytes | str]
    ) -> str:
        """Route audio to local faster-whisper (no network)."""
        if self._whisper_local is None:
            self._whisper_local = WhisperLocalEngine(language=self.transcription_language)
        return await self._whisper_local.transcribe_stream(audio_stream)
