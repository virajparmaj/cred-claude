"""Tests for lightweight app-level display helpers."""

from __future__ import annotations

import datetime

from credclaude.time_utils import fmt_datetime, fmt_relative


class TestFmtRelative:
    def test_far_future_countdown_hidden(self):
        dt = datetime.datetime.now().astimezone() + datetime.timedelta(hours=24)
        assert fmt_relative(dt) == "--"

    def test_near_future_countdown_shown(self):
        dt = datetime.datetime.now().astimezone() + datetime.timedelta(hours=2, minutes=10)
        assert fmt_relative(dt) != "--"


class TestFmtDatetime:
    def test_none_returns_dash(self):
        assert fmt_datetime(None) == "--"

    def test_formats_with_date_and_time(self):
        dt = datetime.datetime(2026, 4, 7, 0, 0, 0, tzinfo=datetime.timezone.utc)
        result = fmt_datetime(dt)
        assert "Apr" in result
        assert "7" in result
        assert ":" in result

    def test_naive_datetime_handled(self):
        dt = datetime.datetime(2026, 4, 7, 14, 30, 0)
        result = fmt_datetime(dt)
        assert result != "--"
        assert "Apr" in result
