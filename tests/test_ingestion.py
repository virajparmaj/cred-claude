"""Tests for JSONL ingestion and scanning."""

from __future__ import annotations

import datetime
import json
import os

import pytest

from credclaude.ingestion import scan_cost_for_date_range, estimate_five_hour_window
from tests.conftest import SAMPLE_RATES, make_assistant_entry, make_user_entry


@pytest.fixture
def session_dir(tmp_path):
    """Create a mock projects directory with session files."""
    project = tmp_path / "test-project"
    project.mkdir()
    return project


def _write_jsonl(path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n")


class TestScanCostForDateRange:
    def test_counts_assistant_entries(self, session_dir):
        f = session_dir / "session.jsonl"
        _write_jsonl(f, [
            make_assistant_entry(input_tokens=1000, output_tokens=500, timestamp="2026-03-20T12:00:00Z"),
            make_assistant_entry(input_tokens=2000, output_tokens=1000, timestamp="2026-03-20T14:00:00Z"),
        ])
        data, stats = scan_cost_for_date_range(
            datetime.date(2026, 3, 20),
            datetime.date(2026, 3, 20),
            SAMPLE_RATES,
            projects_dir=session_dir.parent,
        )
        assert data.message_count == 2
        assert data.total_cost > 0
        assert stats.records_parsed == 2
        assert stats.records_skipped == 0

    def test_skips_user_entries(self, session_dir):
        f = session_dir / "session.jsonl"
        _write_jsonl(f, [
            make_user_entry("2026-03-20T12:00:00Z"),
            make_assistant_entry(timestamp="2026-03-20T12:00:00Z"),
        ])
        data, stats = scan_cost_for_date_range(
            datetime.date(2026, 3, 20),
            datetime.date(2026, 3, 20),
            SAMPLE_RATES,
            projects_dir=session_dir.parent,
        )
        assert data.message_count == 1

    def test_skips_malformed_json(self, session_dir):
        f = session_dir / "session.jsonl"
        _write_jsonl(f, [
            "this is not json",
            make_assistant_entry(timestamp="2026-03-20T12:00:00Z"),
        ])
        data, stats = scan_cost_for_date_range(
            datetime.date(2026, 3, 20),
            datetime.date(2026, 3, 20),
            SAMPLE_RATES,
            projects_dir=session_dir.parent,
        )
        assert data.message_count == 1
        assert stats.records_skipped == 1

    def test_date_filtering(self, session_dir):
        f = session_dir / "session.jsonl"
        _write_jsonl(f, [
            make_assistant_entry(timestamp="2026-03-19T12:00:00Z"),  # yesterday
            make_assistant_entry(timestamp="2026-03-20T12:00:00Z"),  # today
            make_assistant_entry(timestamp="2026-03-21T12:00:00Z"),  # tomorrow
        ])
        data, stats = scan_cost_for_date_range(
            datetime.date(2026, 3, 20),
            datetime.date(2026, 3, 20),
            SAMPLE_RATES,
            projects_dir=session_dir.parent,
        )
        assert data.message_count == 1

    def test_file_cache_hit(self, session_dir):
        f = session_dir / "session.jsonl"
        _write_jsonl(f, [
            make_assistant_entry(timestamp="2026-03-20T12:00:00Z"),
        ])
        cache: dict = {}

        # First scan — populates cache
        data1, _ = scan_cost_for_date_range(
            datetime.date(2026, 3, 20),
            datetime.date(2026, 3, 20),
            SAMPLE_RATES,
            file_cache=cache,
            projects_dir=session_dir.parent,
        )

        # Second scan — should use cache
        data2, stats2 = scan_cost_for_date_range(
            datetime.date(2026, 3, 20),
            datetime.date(2026, 3, 20),
            SAMPLE_RATES,
            file_cache=cache,
            projects_dir=session_dir.parent,
        )

        assert data1.total_cost == pytest.approx(data2.total_cost)
        assert len(cache) == 1

    def test_cache_invalidated_on_size_change(self, session_dir):
        f = session_dir / "session.jsonl"
        _write_jsonl(f, [
            make_assistant_entry(timestamp="2026-03-20T12:00:00Z"),
        ])
        cache: dict = {}

        # First scan
        scan_cost_for_date_range(
            datetime.date(2026, 3, 20),
            datetime.date(2026, 3, 20),
            SAMPLE_RATES,
            file_cache=cache,
            projects_dir=session_dir.parent,
        )

        # Append to file (changes size)
        with open(f, "a") as fh:
            fh.write(make_assistant_entry(
                input_tokens=5000, timestamp="2026-03-20T13:00:00Z"
            ) + "\n")

        data2, _ = scan_cost_for_date_range(
            datetime.date(2026, 3, 20),
            datetime.date(2026, 3, 20),
            SAMPLE_RATES,
            file_cache=cache,
            projects_dir=session_dir.parent,
        )
        assert data2.message_count == 2

    def test_model_breakdown(self, session_dir):
        f = session_dir / "session.jsonl"
        _write_jsonl(f, [
            make_assistant_entry(model="claude-opus-4-6", input_tokens=1000, timestamp="2026-03-20T12:00:00Z"),
            make_assistant_entry(model="claude-sonnet-4-6", input_tokens=1000, timestamp="2026-03-20T12:00:00Z"),
        ])
        data, _ = scan_cost_for_date_range(
            datetime.date(2026, 3, 20),
            datetime.date(2026, 3, 20),
            SAMPLE_RATES,
            projects_dir=session_dir.parent,
        )
        assert "opus" in data.by_model
        assert "sonnet" in data.by_model

    def test_empty_directory(self, session_dir):
        data, stats = scan_cost_for_date_range(
            datetime.date(2026, 3, 20),
            datetime.date(2026, 3, 20),
            SAMPLE_RATES,
            projects_dir=session_dir.parent,
        )
        assert data.total_cost == 0.0
        assert data.message_count == 0


class TestEstimateFiveHourWindow:
    def test_with_recent_entries(self, session_dir):
        f = session_dir / "session.jsonl"
        now = datetime.datetime.now(datetime.timezone.utc)
        recent_ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        _write_jsonl(f, [
            make_assistant_entry(
                input_tokens=5000, output_tokens=2000,
                timestamp=recent_ts,
            ),
        ])
        window = estimate_five_hour_window(SAMPLE_RATES, projects_dir=session_dir.parent)
        assert window.tokens_used > 0

    def test_with_no_entries(self, session_dir):
        window = estimate_five_hour_window(SAMPLE_RATES, projects_dir=session_dir.parent)
        assert window.tokens_used == 0
        assert window.window_start is None
