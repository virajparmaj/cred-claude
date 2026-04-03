"""Data models for CredClaude."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum


@dataclass
class ModelCost:
    """Per-model cost and token breakdown."""

    cost: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_create_tokens: int = 0
    messages: int = 0


@dataclass
class CostData:
    """Aggregated cost data across all models."""

    total_cost: float = 0.0
    by_model: dict[str, ModelCost] = field(default_factory=dict)
    message_count: int = 0


@dataclass
class ScanStats:
    """Diagnostics from a JSONL scan pass."""

    files_scanned: int = 0
    records_parsed: int = 0
    records_skipped: int = 0
    errors: list[str] = field(default_factory=list)


class Confidence(Enum):
    """Confidence level for limit/budget estimates."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ProviderState(Enum):
    """State of a limit data provider."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALE = "stale"
    OFFLINE = "offline"


@dataclass
class WindowInfo:
    """5-hour rolling window usage estimate."""

    tokens_used: int = 0
    window_start: datetime.datetime | None = None
    estimated_remaining_pct: float | None = None
    confidence: Confidence = Confidence.LOW


@dataclass
class LimitInfo:
    """Account limit information from a provider."""

    source: str = "estimated"
    plan_tier: str = "unknown"
    daily_budget_usd: float = 0.0
    confidence: Confidence = Confidence.LOW
    state: ProviderState = ProviderState.OFFLINE
    last_sync: datetime.datetime | None = None
    five_hour_window: WindowInfo | None = None
    weekly_cap_note: str = "Weekly cap may apply (not tracked locally)"
    error: str | None = None
    # Session limit fields (from OAuth API)
    utilization_pct: float | None = None          # Real % from API (0–100)
    resets_at: datetime.datetime | None = None     # When the 5-hour window resets
    # Weekly limit fields (from OAuth API — None when not applicable, e.g. student accounts)
    weekly_utilization_pct: float | None = None
    weekly_resets_at: datetime.datetime | None = None
    # Auto-detected plan info from Keychain OAuth metadata
    subscription_type: str | None = None           # e.g. "pro", "max", "student"
    rate_limit_tier: str | None = None             # e.g. "default_claude_ai"
    # Extra usage / API credits (from OAuth API — None when not enabled)
    extra_usage_enabled: bool | None = None
    extra_usage_monthly_limit: float | None = None
    extra_usage_used: float | None = None
    extra_usage_utilization: float | None = None
