"""JSONL session file scanning, cost aggregation, and 5-hour window estimation."""

from __future__ import annotations

import datetime
import glob
import json
import logging
import os
from pathlib import Path

from credclaude.config import PROJECTS_DIR
from credclaude.cost_engine import (
    compute_message_cost,
    get_model_family,
    parse_timestamp_to_local_date,
    parse_timestamp_to_local_datetime,
)
from credclaude.models import CostData, ModelCost, ScanStats, WindowInfo, Confidence

logger = logging.getLogger("credclaude.ingestion")


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------
def find_session_files(projects_dir: Path | None = None) -> list[str]:
    """Find all Claude session JSONL files."""
    base = projects_dir or PROJECTS_DIR
    patterns = [
        str(base / "*" / "*.jsonl"),
        str(base / "*" / "*" / "subagents" / "*.jsonl"),
    ]
    files: list[str] = []
    for pat in patterns:
        files.extend(glob.glob(pat))
    return files


def _merge_model_cost(target: dict[str, ModelCost], source: dict[str, ModelCost]) -> None:
    """Merge source model costs into target dict in-place."""
    for fam, mc in source.items():
        if fam not in target:
            target[fam] = ModelCost()
        rm = target[fam]
        rm.cost += mc.cost
        rm.input_tokens += mc.input_tokens
        rm.output_tokens += mc.output_tokens
        rm.cache_read_tokens += mc.cache_read_tokens
        rm.cache_create_tokens += mc.cache_create_tokens
        rm.messages += mc.messages


# ---------------------------------------------------------------------------
# Main scanner
# ---------------------------------------------------------------------------
def scan_cost_for_date_range(
    start_date: datetime.date,
    end_date: datetime.date,
    rates: dict[str, dict[str, float]],
    file_cache: dict | None = None,
    projects_dir: Path | None = None,
) -> tuple[CostData, ScanStats]:
    """Scan session files for cost data within a date range (inclusive).

    Returns (CostData, ScanStats).
    """
    result = CostData()
    stats = ScanStats()

    start_epoch = datetime.datetime.combine(
        start_date, datetime.time.min
    ).timestamp()

    for filepath in find_session_files(projects_dir):
        stats.files_scanned += 1
        try:
            mtime = os.path.getmtime(filepath)
            if mtime < start_epoch:
                continue

            fsize = os.path.getsize(filepath)

            # Check cache
            if file_cache is not None and filepath in file_cache:
                cached_size, cached_data = file_cache[filepath]
                if cached_size == fsize:
                    result.total_cost += cached_data.total_cost
                    result.message_count += cached_data.message_count
                    _merge_model_cost(result.by_model, cached_data.by_model)
                    stats.records_parsed += cached_data.message_count
                    continue

            # Parse fresh
            file_data = CostData()
            with open(filepath) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError as e:
                        logger.debug("Skipped malformed JSONL in %s: %s", filepath, e)
                        stats.records_skipped += 1
                        continue

                    if entry.get("type") != "assistant":
                        continue
                    msg = entry.get("message", {})
                    usage = msg.get("usage")
                    model = msg.get("model", "")
                    ts = entry.get("timestamp", "")
                    if not usage or not model or not ts:
                        continue

                    entry_date = parse_timestamp_to_local_date(ts)
                    if entry_date is None:
                        stats.records_skipped += 1
                        continue
                    if entry_date < start_date or entry_date > end_date:
                        continue

                    cost, tokens = compute_message_cost(usage, model, rates)
                    fam = get_model_family(model)

                    file_data.total_cost += cost
                    file_data.message_count += 1
                    if fam not in file_data.by_model:
                        file_data.by_model[fam] = ModelCost()
                    mc = file_data.by_model[fam]
                    mc.cost += cost
                    mc.input_tokens += tokens["input"]
                    mc.output_tokens += tokens["output"]
                    mc.cache_read_tokens += tokens["cache_read"]
                    mc.cache_create_tokens += tokens["cache_create"]
                    mc.messages += 1
                    stats.records_parsed += 1

            # Merge into result
            result.total_cost += file_data.total_cost
            result.message_count += file_data.message_count
            _merge_model_cost(result.by_model, file_data.by_model)

            # Cache
            if file_cache is not None:
                file_cache[filepath] = (fsize, file_data)

        except Exception as e:
            stats.records_skipped += 1
            stats.errors.append(f"{filepath}: {e}")
            logger.warning("Error scanning %s: %s", filepath, e)

    logger.debug(
        "Scan complete: %d files, %d parsed, %d skipped, %d errors",
        stats.files_scanned, stats.records_parsed,
        stats.records_skipped, len(stats.errors),
    )
    return result, stats


# ---------------------------------------------------------------------------
# 5-hour window estimator
# ---------------------------------------------------------------------------
def estimate_five_hour_window(
    rates: dict[str, dict[str, float]],
    projects_dir: Path | None = None,
) -> WindowInfo:
    """Estimate token usage in the last 5 hours from local JSONL files.

    This is a best-effort estimate — the actual server-side remaining
    quota is not available locally.
    """
    now = datetime.datetime.now().astimezone()
    window_start = now - datetime.timedelta(hours=5)
    total_tokens = 0
    found_any = False

    for filepath in find_session_files(projects_dir):
        try:
            mtime = os.path.getmtime(filepath)
            if mtime < window_start.timestamp():
                continue

            with open(filepath) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug("Skipped malformed JSONL in 5h scan: %s", filepath)
                        continue

                    if entry.get("type") != "assistant":
                        continue
                    msg = entry.get("message", {})
                    usage = msg.get("usage")
                    ts = entry.get("timestamp", "")
                    if not usage or not ts:
                        continue

                    entry_dt = parse_timestamp_to_local_datetime(ts)
                    if entry_dt is None or entry_dt < window_start:
                        continue

                    inp = usage.get("input_tokens", 0)
                    out = usage.get("output_tokens", 0)
                    cache_rd = usage.get("cache_read_input_tokens", 0)
                    cache_cr = usage.get("cache_creation_input_tokens", 0)
                    total_tokens += inp + out + cache_rd + cache_cr
                    found_any = True

        except Exception as e:
            logger.debug("Error reading %s for 5h window: %s", filepath, e)

    return WindowInfo(
        tokens_used=total_tokens,
        window_start=window_start if found_any else None,
        estimated_remaining_pct=None,  # Cannot estimate without knowing quota
        confidence=Confidence.MEDIUM if found_any else Confidence.LOW,
    )
