"""Time formatting utilities used by UI layers."""

from __future__ import annotations

import datetime

MAX_DISPLAY_COUNTDOWN_SEC = 12 * 3600


def fmt_relative(dt: datetime.datetime | None) -> str:
    """Format a future datetime as 'Xh Ym' countdown."""
    if dt is None:
        return "--"
    now = datetime.datetime.now().astimezone()
    if dt.tzinfo is None:
        dt = dt.astimezone()
    delta = dt - now
    total_sec = max(0, int(delta.total_seconds()))
    if total_sec > MAX_DISPLAY_COUNTDOWN_SEC:
        return "--"
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    if h == 0:
        return f"{m}m"
    return f"{h}h {m}m"
