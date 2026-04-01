"""Tests for lightweight app-level display helpers."""

from __future__ import annotations

import datetime

from credclaude.time_utils import fmt_relative


class TestFmtRelative:
    def test_far_future_countdown_hidden(self):
        dt = datetime.datetime.now().astimezone() + datetime.timedelta(hours=24)
        assert fmt_relative(dt) == "--"

    def test_near_future_countdown_shown(self):
        dt = datetime.datetime.now().astimezone() + datetime.timedelta(hours=2, minutes=10)
        assert fmt_relative(dt) != "--"
