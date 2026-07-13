"""Shared utility helpers."""

from __future__ import annotations


def safe_divide(numerator: float | int | None, denominator: float | int | None) -> float | None:
    """Return numerator / denominator, or None when division is not meaningful."""
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)
