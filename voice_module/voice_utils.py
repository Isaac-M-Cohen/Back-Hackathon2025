"""Utility helpers for voice processing."""

import re


def normalize_phrase(phrase: str) -> str:
    """Normalize spoken text for easier matching."""
    return re.sub(r"\s+", " ", phrase.strip().lower())
