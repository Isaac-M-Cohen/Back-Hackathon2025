"""CLI for fw_transcribe."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Literal

from fw_transcribe.core import TranscriptionResult, transcribe_file

OutputFormat = Literal["text", "segments", "json"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Transcribe audio with faster-whisper.")
    parser.add_argument("input", help="Path to input audio file (e.g., mp3, wav).")
    parser.add_argument("--model", default="large-v3", help="Model size or local path.")
    parser.add_argument("--device", default="cpu", help="Device: cpu, cuda, or auto.")
    parser.add_argument(
        "--compute-type",
        default="int8",
        help="Compute type: int8, float16, int8_float16, etc.",
    )
    parser.add_argument("--beam-size", type=int, default=5, help="Beam size for decoding.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=0,
        help="If > 0, use BatchedInferencePipeline with this batch size.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "segments", "json"],
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging for faster_whisper.",
    )
    return parser


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if verbose:
        logging.getLogger("faster_whisper").setLevel(logging.DEBUG)


def _render_text(result: TranscriptionResult) -> str:
    return result.text


def _render_segments(result: TranscriptionResult) -> str:
    lines = []
    for seg in result.segments:
        lines.append(f"[{seg.start:.2f} -> {seg.end:.2f}] {seg.text}")
    return "\n".join(lines)


def _render_json(result: TranscriptionResult) -> str:
    payload = {
        "language": result.language,
        "language_probability": result.language_probability,
        "text": result.text,
        "segments": [
            {"start": seg.start, "end": seg.end, "text": seg.text}
            for seg in result.segments
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _print_language_info(result: TranscriptionResult) -> None:
    print(
        f"Detected language: {result.language} "
        f"(prob={result.language_probability:.2f})"
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    try:
        result = transcribe_file(
            args.input,
            model_size=args.model,
            device=args.device,
            compute_type=args.compute_type,
            beam_size=args.beam_size,
            batch_size=args.batch_size,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    _print_language_info(result)

    fmt: OutputFormat = args.format
    if fmt == "json":
        print(_render_json(result))
    elif fmt == "segments":
        print(_render_segments(result))
    else:
        print(_render_text(result))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
