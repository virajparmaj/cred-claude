"""Tests for billing period logic."""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest

from credclaude.billing import (
    billing_period_start,
    next_billing_reset,
    reset_countdown,
)


class TestBillingPeriodStart:
    @patch("credclaude.billing.datetime")
    def test_day_past_in_month(self, mock_dt):
        """Billing day 1, today is the 20th → period started this month."""
        mock_dt.date.today.return_value = datetime.date(2026, 3, 20)
        mock_dt.date.side_effect = datetime.date
        result = billing_period_start(1)
        assert result == datetime.date(2026, 3, 1)

    @patch("credclaude.billing.datetime")
    def test_day_future_in_month(self, mock_dt):
        """Billing day 25, today is the 20th → period started last month."""
        mock_dt.date.today.return_value = datetime.date(2026, 3, 20)
        mock_dt.date.side_effect = datetime.date
        result = billing_period_start(25)
        assert result == datetime.date(2026, 2, 25)

    @patch("credclaude.billing.datetime")
    def test_on_billing_day(self, mock_dt):
        """Today is the billing day → period starts today."""
        mock_dt.date.today.return_value = datetime.date(2026, 3, 15)
        mock_dt.date.side_effect = datetime.date
        result = billing_period_start(15)
        assert result == datetime.date(2026, 3, 15)

    @patch("credclaude.billing.datetime")
    def test_year_boundary(self, mock_dt):
        """Billing day 25, today is Jan 10 → period started Dec 25 previous year."""
        mock_dt.date.today.return_value = datetime.date(2026, 1, 10)
        mock_dt.date.side_effect = datetime.date
        result = billing_period_start(25)
        assert result == datetime.date(2025, 12, 25)

    @patch("credclaude.billing.datetime")
    def test_feb_30_fallback(self, mock_dt):
        """Billing day 30, going back to Feb → falls back to Feb 1."""
        mock_dt.date.today.return_value = datetime.date(2026, 3, 10)
        mock_dt.date.side_effect = datetime.date
        result = billing_period_start(30)
        assert result == datetime.date(2026, 2, 1)


class TestNextBillingReset:
    @patch("credclaude.billing.datetime")
    def test_before_billing_day(self, mock_dt):
        """Today is 10th, billing day 15 → resets on the 15th this month."""
        mock_dt.date.today.return_value = datetime.date(2026, 3, 10)
        mock_dt.date.side_effect = datetime.date
        mock_dt.datetime = datetime.datetime
        mock_dt.time = datetime.time
        result = next_billing_reset(15)
        assert result == datetime.datetime(2026, 3, 15, 0, 0)

    @patch("credclaude.billing.datetime")
    def test_on_billing_day(self, mock_dt):
        """Today is 15th, billing day 15 → resets next month."""
        mock_dt.date.today.return_value = datetime.date(2026, 3, 15)
        mock_dt.date.side_effect = datetime.date
        mock_dt.datetime = datetime.datetime
        mock_dt.time = datetime.time
        result = next_billing_reset(15)
        assert result == datetime.datetime(2026, 4, 15, 0, 0)

    @patch("credclaude.billing.datetime")
    def test_december_to_january(self, mock_dt):
        """Billing day 15, today is Dec 20 → resets Jan 15 next year."""
        mock_dt.date.today.return_value = datetime.date(2026, 12, 20)
        mock_dt.date.side_effect = datetime.date
        mock_dt.datetime = datetime.datetime
        mock_dt.time = datetime.time
        result = next_billing_reset(15)
        assert result == datetime.datetime(2027, 1, 15, 0, 0)

    @patch("credclaude.billing.datetime")
    def test_day_31_in_short_month(self, mock_dt):
        """Billing day 31, today is Jan 15 → resets Jan 31."""
        mock_dt.date.today.return_value = datetime.date(2026, 1, 15)
        mock_dt.date.side_effect = datetime.date
        mock_dt.datetime = datetime.datetime
        mock_dt.time = datetime.time
        result = next_billing_reset(31)
        assert result == datetime.datetime(2026, 1, 31, 0, 0)


class TestResetCountdown:
    def test_returns_tuple_of_three(self):
        d, h, m = reset_countdown(1)
        assert isinstance(d, int)
        assert isinstance(h, int)
        assert isinstance(m, int)
        assert d >= 0 and h >= 0 and m >= 0
