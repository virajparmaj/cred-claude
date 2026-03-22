"""Configuration management, paths, and logging setup."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

logger = logging.getLogger("credclaude")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CLAUDE_DIR = Path.home() / ".claude"
APP_DIR = Path.home() / ".credclaude"
CONFIG_PATH = APP_DIR / "config.json"
PRICING_PATH = APP_DIR / "pricing.json"
LOG_PATH = APP_DIR / "monitor.log"
PROJECTS_DIR = CLAUDE_DIR / "projects"
NOTIF_LOCK_PATH = APP_DIR / ".last_reset_notif"
SNAPSHOT_PATH = APP_DIR / "last_usage.json"

# ---------------------------------------------------------------------------
# Intervals
# ---------------------------------------------------------------------------
REFRESH_INTERVAL_SEC = 60   # Poll every 60 seconds
NOTIF_CHECK_INTERVAL_SEC = 1800  # 30 minutes

# ---------------------------------------------------------------------------
# Default config
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: dict = {
    "billing_day": 1,
    "daily_budget_usd": None,  # None = use plan tier estimate; float = manual override
    "warn_at_pct": 80,
    "notifications_enabled": True,
    "plan_tier": "pro",  # "pro" | "max_5x" | "max_20x"
    "stale_threshold_minutes": 30,
    "refresh_interval_sec": 60,
}


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------
def load_config() -> dict:
    """Load config from disk, migrating old keys and backfilling defaults."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            # Migrate old config
            if "daily_message_limit" in cfg and "daily_budget_usd" not in cfg:
                cfg["daily_budget_usd"] = DEFAULT_CONFIG["daily_budget_usd"]
                del cfg["daily_message_limit"]
                logger.info("Migrated config: removed daily_message_limit")
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            # Validate types — reset to defaults if corrupt
            if not isinstance(cfg.get("billing_day"), int):
                logger.warning("Invalid billing_day type (%s), resetting to default",
                               type(cfg.get("billing_day")).__name__)
                cfg["billing_day"] = DEFAULT_CONFIG["billing_day"]
            if not isinstance(cfg.get("warn_at_pct"), (int, float)):
                logger.warning("Invalid warn_at_pct type (%s), resetting to default",
                               type(cfg.get("warn_at_pct")).__name__)
                cfg["warn_at_pct"] = DEFAULT_CONFIG["warn_at_pct"]
            if cfg.get("plan_tier") not in ("pro", "max_5x", "max_20x"):
                logger.warning("Invalid plan_tier '%s', resetting to default",
                               cfg.get("plan_tier"))
                cfg["plan_tier"] = DEFAULT_CONFIG["plan_tier"]
            return cfg
        except Exception as e:
            logger.warning("Failed to load config, using defaults: %s", e)
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict) -> None:
    """Persist config to disk."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
def setup_logging() -> None:
    """Configure rotating file + stderr logging."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger("credclaude")
    root_logger.setLevel(logging.DEBUG)

    # File handler — rotating, 5 MB, 2 backups
    fh = RotatingFileHandler(str(LOG_PATH), maxBytes=5_000_000, backupCount=2)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    root_logger.addHandler(fh)

    # Stderr handler — warnings and above
    sh = logging.StreamHandler()
    sh.setLevel(logging.WARNING)
    sh.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root_logger.addHandler(sh)
