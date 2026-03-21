"""Billing period helpers — pure functions for date math."""

from __future__ import annotations

import calendar
import datetime


def billing_period_start(billing_day: int) -> datetime.date:
    """Find the start date of the current billing period."""
    today = datetime.date.today()
    if today.day >= billing_day:
        try:
            return datetime.date(today.year, today.month, billing_day)
        except ValueError:
            return datetime.date(today.year, today.month, 1)
    else:
        m = today.month - 1 or 12
        y = today.year if today.month > 1 else today.year - 1
        try:
            return datetime.date(y, m, billing_day)
        except ValueError:
            return datetime.date(y, m, 1)


def next_billing_reset(billing_day: int) -> datetime.datetime:
    """Find the next billing reset as a datetime (midnight)."""
    today = datetime.date.today()
    year, month = today.year, today.month

    def make_date(y: int, m: int, d: int) -> datetime.date:
        last = calendar.monthrange(y, m)[1]
        return datetime.date(y, m, min(d, last))

    if today.day < billing_day:
        reset_date = make_date(year, month, billing_day)
    else:
        nm = month % 12 + 1
        ny = year + (1 if month == 12 else 0)
        reset_date = make_date(ny, nm, billing_day)

    return datetime.datetime.combine(reset_date, datetime.time.min)


def reset_countdown(billing_day: int) -> tuple[int, int, int]:
    """Return (days, hours, minutes) until next billing reset."""
    delta = next_billing_reset(billing_day) - datetime.datetime.now()
    total = max(0, int(delta.total_seconds()))
    d = total // 86400
    h = (total % 86400) // 3600
    m = (total % 3600) // 60
    return d, h, m
