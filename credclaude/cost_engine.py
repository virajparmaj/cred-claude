"""Pricing, model family detection, and per-message cost computation."""

from __future__ import annotations

import datetime
import json
import logging
from importlib import resources
from pathlib import Path

from credclaude.config import PRICING_PATH

logger = logging.getLogger("credclaude.cost_engine")

# ---------------------------------------------------------------------------
# Built-in fallback rates (used if no pricing file exists)
# ---------------------------------------------------------------------------
_BUILTIN_RATES: dict[str, dict[str, float]] = {
    "opus": {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_create": 18.75},
    "sonnet": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_create": 3.75},
    "haiku": {"input": 1.0, "output": 5.0, "cache_read": 0.10, "cache_create": 1.25},
}


# ---------------------------------------------------------------------------
# Pricing loader
# ---------------------------------------------------------------------------
def load_pricing(pricing_path: Path | None = None) -> dict:
    """Load pricing data from disk, falling back to shipped defaults.

    Returns dict with keys: 'rates', 'updated_at', 'source'.
    """
    path = pricing_path or PRICING_PATH
    if path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
            if "rates" in data:
                logger.debug("Loaded pricing from %s", path)
                return data
            logger.warning("Pricing file missing 'rates' key: %s", path)
        except Exception as e:
            logger.warning("Failed to load pricing from %s: %s", path, e)

    # Fall back to shipped default_pricing.json
    try:
        ref = resources.files("credclaude").joinpath("default_pricing.json")
        data = json.loads(ref.read_text(encoding="utf-8"))
        logger.info("Using shipped default pricing")
        return data
    except Exception as e:
        logger.warning("Failed to load shipped pricing, using builtin: %s", e)

    return {
        "rates": _BUILTIN_RATES,
        "updated_at": "2026-03-20",
        "source": "builtin",
    }


def save_default_pricing(pricing_path: Path | None = None) -> None:
    """Copy shipped default pricing to the user's config dir."""
    path = pricing_path or PRICING_PATH
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        ref = resources.files("credclaude").joinpath("default_pricing.json")
        path.write_text(ref.read_text(encoding="utf-8"), encoding="utf-8")
        logger.info("Saved default pricing to %s", path)
    except Exception as e:
        logger.warning("Could not save default pricing: %s", e)


def check_pricing_staleness(pricing_data: dict, max_age_days: int = 30) -> bool:
    """Return True if pricing data is older than max_age_days."""
    updated_at = pricing_data.get("updated_at", "")
    if not updated_at:
        return True
    try:
        updated_date = datetime.date.fromisoformat(updated_at)
        age = (datetime.date.today() - updated_date).days
        return age > max_age_days
    except (ValueError, TypeError):
        return True


def get_rates(pricing_data: dict) -> dict[str, dict[str, float]]:
    """Extract the rates dict from pricing data."""
    return pricing_data.get("rates", _BUILTIN_RATES)


# ---------------------------------------------------------------------------
# Model family
# ---------------------------------------------------------------------------
def get_model_family(model: str) -> str:
    """Extract model family (opus/sonnet/haiku) from a model name string."""
    model_lower = model.lower()
    for fam in ("opus", "sonnet", "haiku"):
        if fam in model_lower:
            return fam
    return "sonnet"  # default fallback


# ---------------------------------------------------------------------------
# Cost computation
# ---------------------------------------------------------------------------
def compute_message_cost(
    usage: dict, model: str, rates: dict[str, dict[str, float]]
) -> tuple[float, dict[str, int]]:
    """Compute USD cost for a single assistant message.

    Returns (cost, token_breakdown).
    """
    fam = get_model_family(model)
    fam_rates = rates.get(fam, rates.get("sonnet", _BUILTIN_RATES["sonnet"]))

    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cache_rd = usage.get("cache_read_input_tokens", 0)
    cache_cr = usage.get("cache_creation_input_tokens", 0)

    cost = (
        inp * fam_rates["input"] / 1_000_000
        + out * fam_rates["output"] / 1_000_000
        + cache_rd * fam_rates["cache_read"] / 1_000_000
        + cache_cr * fam_rates["cache_create"] / 1_000_000
    )
    tokens = {
        "input": inp,
        "output": out,
        "cache_read": cache_rd,
        "cache_create": cache_cr,
    }
    return cost, tokens


# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------
def parse_timestamp_to_local_date(ts_str: str) -> datetime.date | None:
    """Parse ISO 8601 timestamp to local date. Returns None on failure."""
    try:
        dt = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.astimezone().date()
    except Exception as e:
        logger.debug("Failed to parse timestamp '%s': %s", ts_str, e)
        return None


def parse_timestamp_to_local_datetime(ts_str: str) -> datetime.datetime | None:
    """Parse ISO 8601 timestamp to local datetime. Returns None on failure."""
    try:
        dt = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.astimezone()
    except Exception as e:
        logger.debug("Failed to parse timestamp '%s': %s", ts_str, e)
        return None
