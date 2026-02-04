"""Local Whisper transcription using faster-whisper (no network)."""

from __future__ import annotations

import base64
import os
from typing import AsyncIterable, Iterable

import numpy as np

try:
    from faster_whisper import WhisperModel
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError(
        "faster-whisper is required for local whisper transcription. "
        "Install with `pip install faster-whisper` and provide a local model path."
    ) from exc


class WhisperLocalEngine:
    """Run Whisper locally using faster-whisper on CPU/GPU."""

    def __init__(
        self,
        model_path: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
        language: str | None = None,
        sample_rate: int = 16000,
    ) -> None:
        self.model_path = model_path or os.getenv("LOCAL_WHISPER_MODEL_PATH", "small")
        self.device = device or os.getenv("LOCAL_WHISPER_DEVICE", "cpu")
        self.compute_type = compute_type or os.getenv("LOCAL_WHISPER_COMPUTE_TYPE", "int8")
        self.language = language or os.getenv("LOCAL_WHISPER_LANGUAGE", "en")
        self.sample_rate = sample_rate
        self._model: WhisperModel | None = None

    def _ensure_model(self) -> WhisperModel:
        if self._model is None:
            self._model = WhisperModel(
                self.model_path, device=self.device, compute_type=self.compute_type
            )
        return self._model

    async def transcribe_stream(
        self, audio_stream: AsyncIterable[bytes | str] | Iterable[bytes | str]
    ) -> str:
        """Collect PCM16 chunks, run local Whisper, and return text."""
        audio_bytes = bytearray()
        async for chunk in _to_async_iter(audio_stream):
            if not chunk:
                continue
            if isinstance(chunk, str):
                audio_bytes.extend(base64.b64decode(chunk))
            else:
                audio_bytes.extend(chunk)

        if not audio_bytes:
            return ""
        return self.transcribe_audio_bytes(bytes(audio_bytes))

    def transcribe_audio_bytes(self, audio_bytes: bytes) -> str:
        """Run local Whisper on raw PCM16 bytes and return text."""
        if not audio_bytes:
            return ""

        # Convert raw PCM16 bytes to float32 numpy array scaled to [-1, 1].
        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_float = audio_int16.astype(np.float32) / 32768.0

        model = self._ensure_model()
        segments, _info = model.transcribe(
            audio=audio_float,
            language=self.language,
            beam_size=3,
            vad_filter=True,
        )
        parts: list[str] = []
        for seg in segments:
            if seg.text:
                parts.append(seg.text.strip())
        return " ".join(parts).strip()


async def _to_async_iter(stream: AsyncIterable[bytes | str] | Iterable[bytes | str]):
    if hasattr(stream, "__aiter__"):
        async for item in stream:  # type: ignore[operator]
            yield item
    else:
        for item in stream:
            yield item
