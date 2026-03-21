"""Tests for cost_engine module."""

from __future__ import annotations

import datetime
import json
import pytest

from credclaude.cost_engine import (
    check_pricing_staleness,
    compute_message_cost,
    get_model_family,
    load_pricing,
    parse_timestamp_to_local_date,
)
from tests.conftest import SAMPLE_RATES


# ---------------------------------------------------------------------------
# get_model_family
# ---------------------------------------------------------------------------
class TestGetModelFamily:
    def test_opus(self):
        assert get_model_family("claude-opus-4-6") == "opus"

    def test_sonnet(self):
        assert get_model_family("claude-sonnet-4-6") == "sonnet"

    def test_haiku(self):
        assert get_model_family("claude-3-5-haiku-20241022") == "haiku"

    def test_case_insensitive(self):
        assert get_model_family("Claude-OPUS-4-6") == "opus"

    def test_unknown_defaults_to_sonnet(self):
        assert get_model_family("some-unknown-model") == "sonnet"

    def test_empty_string(self):
        assert get_model_family("") == "sonnet"


# ---------------------------------------------------------------------------
# compute_message_cost
# ---------------------------------------------------------------------------
class TestComputeMessageCost:
    def test_sonnet_basic(self):
        usage = {"input_tokens": 1_000_000, "output_tokens": 0}
        cost, tokens = compute_message_cost(usage, "claude-sonnet-4-6", SAMPLE_RATES)
        assert cost == pytest.approx(3.0)  # 1M * $3/M
        assert tokens["input"] == 1_000_000
        assert tokens["output"] == 0

    def test_opus_output(self):
        usage = {"input_tokens": 0, "output_tokens": 1_000_000}
        cost, _ = compute_message_cost(usage, "claude-opus-4-6", SAMPLE_RATES)
        assert cost == pytest.approx(75.0)  # 1M * $75/M

    def test_haiku_all_fields(self):
        usage = {
            "input_tokens": 100_000,
            "output_tokens": 50_000,
            "cache_read_input_tokens": 200_000,
            "cache_creation_input_tokens": 10_000,
        }
        cost, tokens = compute_message_cost(usage, "claude-haiku-4-5", SAMPLE_RATES)
        expected = (
            100_000 * 1.0 / 1e6
            + 50_000 * 5.0 / 1e6
            + 200_000 * 0.10 / 1e6
            + 10_000 * 1.25 / 1e6
        )
        assert cost == pytest.approx(expected)
        assert tokens["cache_read"] == 200_000
        assert tokens["cache_create"] == 10_000

    def test_zero_tokens(self):
        usage = {}
        cost, tokens = compute_message_cost(usage, "claude-sonnet-4-6", SAMPLE_RATES)
        assert cost == 0.0
        assert tokens["input"] == 0

    def test_unknown_model_uses_sonnet_rates(self):
        usage = {"input_tokens": 1_000_000}
        cost, _ = compute_message_cost(usage, "mystery-model", SAMPLE_RATES)
        assert cost == pytest.approx(3.0)  # sonnet input rate


# ---------------------------------------------------------------------------
# parse_timestamp_to_local_date
# ---------------------------------------------------------------------------
class TestParseTimestamp:
    def test_valid_z_suffix(self):
        result = parse_timestamp_to_local_date("2026-03-20T12:00:00Z")
        assert isinstance(result, datetime.date)

    def test_valid_offset(self):
        result = parse_timestamp_to_local_date("2026-03-20T12:00:00+05:30")
        assert isinstance(result, datetime.date)

    def test_invalid_returns_none(self):
        assert parse_timestamp_to_local_date("not-a-date") is None

    def test_empty_returns_none(self):
        assert parse_timestamp_to_local_date("") is None


# ---------------------------------------------------------------------------
# Pricing loading and staleness
# ---------------------------------------------------------------------------
class TestPricingLoad:
    def test_load_valid_pricing(self, tmp_path):
        pricing = {
            "updated_at": "2026-03-20",
            "source": "test",
            "rates": SAMPLE_RATES,
        }
        p = tmp_path / "pricing.json"
        p.write_text(json.dumps(pricing))
        result = load_pricing(p)
        assert result["rates"]["opus"]["input"] == 15.0

    def test_load_missing_file_falls_back(self, tmp_path):
        p = tmp_path / "nonexistent.json"
        result = load_pricing(p)
        assert "rates" in result

    def test_load_corrupt_file_falls_back(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not valid json{{{")
        result = load_pricing(p)
        assert "rates" in result


class TestPricingStaleness:
    def test_fresh(self):
        data = {"updated_at": datetime.date.today().isoformat()}
        assert check_pricing_staleness(data) is False

    def test_stale(self):
        old = datetime.date.today() - datetime.timedelta(days=31)
        data = {"updated_at": old.isoformat()}
        assert check_pricing_staleness(data) is True

    def test_just_under_threshold(self):
        d = datetime.date.today() - datetime.timedelta(days=29)
        data = {"updated_at": d.isoformat()}
        assert check_pricing_staleness(data) is False

    def test_missing_updated_at(self):
        assert check_pricing_staleness({}) is True

    def test_invalid_date(self):
        assert check_pricing_staleness({"updated_at": "garbage"}) is True
