"""Speech-to-text engine using faster-whisper."""

from __future__ import annotations

import os
import tempfile
from typing import AsyncIterable, Iterable

from fw_transcribe.core import transcribe_file


class SpeechToTextEngine:
    """Runs local Whisper transcription only."""

    def __init__(
        self,
        default_sample_rate: int = 16000,
    ) -> None:
        self.transcription_language = os.getenv("LOCAL_WHISPER_LANGUAGE", "en")
        self.default_sample_rate = default_sample_rate
        self.provider = (os.getenv("STT_PROVIDER") or "whisper-local").lower()
        self.model_path = os.getenv("LOCAL_WHISPER_MODEL_PATH", "small")
        self.device = os.getenv("LOCAL_WHISPER_DEVICE", "cpu")
        self.compute_type = os.getenv("LOCAL_WHISPER_COMPUTE_TYPE", "int8")
        self.beam_size = int(os.getenv("LOCAL_WHISPER_BEAM_SIZE", "3"))
        self.batch_size = int(os.getenv("LOCAL_WHISPER_BATCH_SIZE", "0"))

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
        raise RuntimeError("Streaming transcription is not supported; use WAV bytes.")

    async def transcribe_audio_bytes(self, audio_bytes: bytes) -> str:
        """Run local Whisper on raw PCM16 audio bytes and return the transcript."""
        if self.provider != "whisper-local":
            raise RuntimeError(
                f"Unsupported STT_PROVIDER '{self.provider}'. Only 'whisper-local' is supported."
            )
        raise RuntimeError("PCM bytes not supported; provide WAV bytes instead.")

    async def transcribe_wav_bytes(self, wav_bytes: bytes) -> str:
        """Run local Whisper on WAV-formatted audio bytes and return the transcript.

        Args:
            wav_bytes: Audio data in WAV format (with headers)

        Returns:
            Transcribed text
        """
        if self.provider != "whisper-local":
            raise RuntimeError(
                f"Unsupported STT_PROVIDER '{self.provider}'. Only 'whisper-local' is supported."
            )
        return await _to_thread(self._transcribe_wav_bytes, wav_bytes)

    def _transcribe_wav_bytes(self, wav_bytes: bytes) -> str:
        if not wav_bytes:
            return ""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(wav_bytes)
            tmp_path = tmp.name
        try:
            return self._transcribe_path(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _transcribe_path(self, audio_path: str) -> str:
        return transcribe_file(
            audio_path,
            model_size=self.model_path,
            device=self.device,
            compute_type=self.compute_type,
            beam_size=self.beam_size,
            batch_size=self.batch_size,
            language=self.transcription_language,
        ).text

    def format_usage(self) -> str | None:
        """Local STT does not report token usage."""
        return None


async def _to_thread(func, *args, **kwargs):
    import asyncio

    return await asyncio.to_thread(func, *args, **kwargs)
