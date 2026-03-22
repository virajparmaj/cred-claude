"""UI formatting helpers — progress bars, token counts, cost strings."""

from __future__ import annotations


def make_bar(pct: float, width: int = 20) -> str:
    """Return a text progress bar like ■■■■■■■■□□□□□□□□□□□□."""
    clamped = max(0, min(100, pct))
    filled = round(clamped / 100 * width)
    return "\u25a0" * filled + "\u25a1" * (width - filled)


def fmt_tokens(n: int) -> str:
    """Format token count: 2.0M, 5.3k, or 42."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def fmt_cost(c: float) -> str:
    """Format USD cost with adaptive precision: $150, $15.3, $5.45."""
    if c >= 100:
        return f"${c:.0f}"
    if c >= 10:
        return f"${c:.1f}"
    return f"${c:.2f}"
