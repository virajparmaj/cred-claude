"""Tests for formatting helpers."""

from __future__ import annotations

from credclaude.formatting import fmt_cost, fmt_tokens, make_bar


class TestMakeBar:
    def test_zero(self):
        assert make_bar(0) == "\u25a1" * 20

    def test_hundred(self):
        assert make_bar(100) == "\u25a0" * 20

    def test_fifty(self):
        bar = make_bar(50)
        assert len(bar) == 20
        assert bar.count("\u25a0") == 10
        assert bar.count("\u25a1") == 10

    def test_over_hundred_clamped(self):
        assert make_bar(150) == "\u25a0" * 20

    def test_negative_clamped(self):
        assert make_bar(-10) == "\u25a1" * 20

    def test_fractional_low(self):
        # 0.1% → round(0.02) = 0 filled
        assert make_bar(0.1) == "\u25a1" * 20

    def test_fractional_high(self):
        # 99.9% → round(19.98) = 20 filled
        assert make_bar(99.9) == "\u25a0" * 20

    def test_rounding_down(self):
        # 52.4% → round(10.48) = 10 filled
        bar = make_bar(52.4)
        assert bar.count("\u25a0") == 10
        assert bar.count("\u25a1") == 10

    def test_rounding_up(self):
        # 52.6% → round(10.52) = 11 filled
        bar = make_bar(52.6)
        assert bar.count("\u25a0") == 11
        assert bar.count("\u25a1") == 9

    def test_custom_width(self):
        bar = make_bar(50, width=10)
        assert len(bar) == 10
        assert bar.count("\u25a0") == 5

    def test_just_below_full(self):
        # 95% → round(19.0) = 19 filled
        bar = make_bar(95)
        assert bar.count("\u25a0") == 19
        assert bar.count("\u25a1") == 1


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

    def test_zero(self):
        assert fmt_tokens(0) == "0"

    def test_just_below_thousand(self):
        assert fmt_tokens(999) == "999"

    def test_just_below_million(self):
        # 999_999 / 1000 = 999.999 → rounds to "1000.0k" (display quirk before M threshold)
        assert fmt_tokens(999_999) == "1000.0k"

    def test_large_millions(self):
        assert fmt_tokens(10_000_000) == "10.0M"


class TestFmtCost:
    def test_small(self):
        assert fmt_cost(5.45) == "$5.45"

    def test_medium(self):
        assert fmt_cost(15.3) == "$15.3"

    def test_large(self):
        assert fmt_cost(150) == "$150"

    def test_zero(self):
        assert fmt_cost(0) == "$0.00"

    def test_just_below_ten(self):
        assert fmt_cost(9.99) == "$9.99"

    def test_exactly_ten(self):
        assert fmt_cost(10.0) == "$10.0"

    def test_just_below_hundred(self):
        # 99.99 >= 10 → 1dp → f"{99.99:.1f}" = "100.0" (float rounding quirk)
        assert fmt_cost(99.99) == "$100.0"

    def test_exactly_hundred(self):
        assert fmt_cost(100.0) == "$100"

    def test_very_small(self):
        assert fmt_cost(0.001) == "$0.00"

    def test_negative(self):
        # No special handling for negatives — documents current behaviour
        assert fmt_cost(-5.0) == "$-5.00"
