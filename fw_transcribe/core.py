"""Core transcription helpers for faster-whisper."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from faster_whisper import BatchedInferencePipeline, WhisperModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Segment:
    """One transcription segment with timestamps."""

    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptionResult:
    """Container for transcription output."""

    language: str
    language_probability: float
    text: str
    segments: Tuple[Segment, ...]


def _build_model(model_size: str, device: str, compute_type: str) -> WhisperModel:
    """Create a WhisperModel with the requested device and compute type."""
    return WhisperModel(model_size, device=device, compute_type=compute_type)


def _iterate_segments(segments_iter: Iterable) -> List[Segment]:
    """Consume the segments generator exactly once."""
    segments: List[Segment] = []
    for seg in segments_iter:
        segments.append(Segment(start=seg.start, end=seg.end, text=seg.text))
    return segments


def transcribe_file(
    audio_path: str,
    *,
    model_size: str = "large-v3",
    device: str = "cpu",
    compute_type: str = "int8",
    beam_size: int = 5,
    batch_size: int = 0,
    language: Optional[str] = None,
) -> TranscriptionResult:
    """Transcribe an audio file to text using faster-whisper.

    Args:
        audio_path: Path to the audio file.
        model_size: Whisper model name or local path.
        device: "cpu", "cuda", or "auto".
        compute_type: "int8", "float16", "int8_float16", etc.
        beam_size: Beam search size for decoding.
        batch_size: If > 0, uses BatchedInferencePipeline.
    """
    model = _build_model(model_size, device, compute_type)

    if batch_size and batch_size > 0:
        logger.debug("Using BatchedInferencePipeline with batch_size=%s", batch_size)
        batched = BatchedInferencePipeline(model=model)
        segments_iter, info = batched.transcribe(
            audio_path,
            batch_size=batch_size,
            language=language,
            beam_size=beam_size,
        )
    else:
        segments_iter, info = model.transcribe(
            audio_path, beam_size=beam_size, language=language
        )

    segments = _iterate_segments(segments_iter)
    text = " ".join(seg.text.strip() for seg in segments if seg.text).strip()
    return TranscriptionResult(
        language=info.language,
        language_probability=info.language_probability,
        text=text,
        segments=tuple(segments),
    )
