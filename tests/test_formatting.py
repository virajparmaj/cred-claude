"""Tests for formatting helpers."""

from __future__ import annotations

from credclaude.formatting import fmt_cost, fmt_tokens, make_bar


class TestMakeBar:
    def test_zero(self):
        assert make_bar(0) == "\u2591" * 20

    def test_hundred(self):
        assert make_bar(100) == "\u2588" * 20

    def test_fifty(self):
        bar = make_bar(50)
        assert len(bar) == 20
        assert bar.count("\u2588") == 10
        assert bar.count("\u2591") == 10

    def test_over_hundred_clamped(self):
        assert make_bar(150) == "\u2588" * 20

    def test_negative_clamped(self):
        assert make_bar(-10) == "\u2591" * 20


class TestFmtTokens:
    def test_small(self):
        assert fmt_tokens(42) == "42"

    def test_thousands(self):
        assert fmt_tokens(1500) == "1.5k"

    def test_millions(self):
        assert fmt_tokens(2_000_000) == "2.0M"

    def test_exact_thousand(self):
        assert fmt_tokens(1000) == "1.0k"

    def test_exact_million(self):
        assert fmt_tokens(1_000_000) == "1.0M"


class TestFmtCost:
    def test_small(self):
        assert fmt_cost(5.45) == "$5.45"

    def test_medium(self):
        assert fmt_cost(15.3) == "$15.3"

    def test_large(self):
        assert fmt_cost(150) == "$150"

    def test_zero(self):
        assert fmt_cost(0) == "$0.00"
