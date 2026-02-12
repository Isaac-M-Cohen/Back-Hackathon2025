"""Local Whisper transcription using faster-whisper (no network)."""

from __future__ import annotations

import base64
import io
import os
import wave
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

        return self._transcribe_audio_array(audio_float)

    def transcribe_wav_bytes(self, wav_bytes: bytes) -> str:
        """Run local Whisper on WAV-formatted bytes and return text.

        Args:
            wav_bytes: Audio data in WAV format (with headers)

        Returns:
            Transcribed text
        """
        if not wav_bytes:
            return ""

        # Parse WAV file to extract raw audio
        wav_buffer = io.BytesIO(wav_bytes)
        try:
            with wave.open(wav_buffer, "rb") as wav_file:
                # Validate format
                n_channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                frame_rate = wav_file.getframerate()
                n_frames = wav_file.getnframes()

                if n_frames == 0:
                    return ""

                # Read raw audio data
                raw_audio = wav_file.readframes(n_frames)

            # Convert to float32 array
            if sample_width == 2:  # 16-bit
                audio_int16 = np.frombuffer(raw_audio, dtype=np.int16)
                audio_float = audio_int16.astype(np.float32) / 32768.0
            elif sample_width == 1:  # 8-bit
                audio_int8 = np.frombuffer(raw_audio, dtype=np.uint8)
                audio_float = (audio_int8.astype(np.float32) - 128) / 128.0
            else:
                # Assume 16-bit for other cases
                audio_int16 = np.frombuffer(raw_audio, dtype=np.int16)
                audio_float = audio_int16.astype(np.float32) / 32768.0

            # Convert stereo to mono if needed
            if n_channels == 2:
                audio_float = audio_float.reshape(-1, 2).mean(axis=1)

            # Resample if needed (faster-whisper expects 16kHz)
            if frame_rate != self.sample_rate:
                audio_float = self._resample(audio_float, frame_rate, self.sample_rate)

            return self._transcribe_audio_array(audio_float)

        except wave.Error:
            # Fallback: try treating as raw PCM16
            return self.transcribe_audio_bytes(wav_bytes)

    def _transcribe_audio_array(self, audio_float: np.ndarray) -> str:
        """Transcribe a float32 audio array using Whisper."""
        if len(audio_float) == 0:
            return ""

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

    def _resample(self, audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """Simple resampling using linear interpolation."""
        if orig_sr == target_sr:
            return audio

        duration = len(audio) / orig_sr
        target_length = int(duration * target_sr)

        if target_length == 0:
            return audio

        # Linear interpolation resampling
        indices = np.linspace(0, len(audio) - 1, target_length)
        resampled = np.interp(indices, np.arange(len(audio)), audio)
        return resampled.astype(np.float32)


async def _to_async_iter(stream: AsyncIterable[bytes | str] | Iterable[bytes | str]):
    if hasattr(stream, "__aiter__"):
        async for item in stream:  # type: ignore[operator]
            yield item
    else:
        for item in stream:
            yield item
