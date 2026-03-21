#!/usr/bin/env python3
"""
DEPRECATED — This single-file version has been replaced by the
credclaude/ package. Kept for reference only.

Use `python -m credclaude` or the installed .app bundle instead.

Original: Claude Code Usage Monitor — macOS Menu Bar App
Tracks daily compute cost from session JSONL files + billing period reset.
"""

import json
import os
import glob
import subprocess
import datetime
import calendar
from dataclasses import dataclass, field
from pathlib import Path

import rumps

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CLAUDE_DIR = Path.home() / ".claude"
APP_DIR = Path.home() / ".credclaude"
CONFIG_PATH = APP_DIR / "config.json"
PROJECTS_DIR = CLAUDE_DIR / "projects"
NOTIF_LOCK_PATH = APP_DIR / ".last_reset_notif"
WARN_LOCK_PATH = APP_DIR / ".last_warn_notif"

REFRESH_INTERVAL_SEC = 300  # 5 minutes
NOTIF_CHECK_INTERVAL_SEC = 1800  # 30 minutes

# ---------------------------------------------------------------------------
# Model pricing (per million tokens, USD)
# ---------------------------------------------------------------------------
MODEL_RATES: dict[str, dict[str, float]] = {
    "opus": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.50,
        "cache_create": 18.75,
    },
    "sonnet": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_create": 3.75,
    },
    "haiku": {
        "input": 0.80,
        "output": 4.0,
        "cache_read": 0.08,
        "cache_create": 1.0,
    },
}

DEFAULT_CONFIG: dict = {
    "billing_day": 1,
    "daily_budget_usd": 100.00,
    "warn_at_pct": 80,
    "notifications_enabled": True,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ModelCost:
    cost: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_create_tokens: int = 0
    messages: int = 0


@dataclass
class CostData:
    total_cost: float = 0.0
    by_model: dict[str, ModelCost] = field(default_factory=dict)
    message_count: int = 0


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            # Migrate old config
            if "daily_message_limit" in cfg and "daily_budget_usd" not in cfg:
                cfg["daily_budget_usd"] = DEFAULT_CONFIG["daily_budget_usd"]
                del cfg["daily_message_limit"]
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ---------------------------------------------------------------------------
# Cost computation
# ---------------------------------------------------------------------------

def get_model_family(model: str) -> str:
    model_lower = model.lower()
    for fam in ("opus", "sonnet", "haiku"):
        if fam in model_lower:
            return fam
    return "sonnet"  # default fallback


def compute_message_cost(usage: dict, model: str) -> tuple[float, dict]:
    """Compute cost for a single message. Returns (cost, token_breakdown)."""
    fam = get_model_family(model)
    rates = MODEL_RATES.get(fam, MODEL_RATES["sonnet"])

    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cache_rd = usage.get("cache_read_input_tokens", 0)
    cache_cr = usage.get("cache_creation_input_tokens", 0)

    cost = (
        inp * rates["input"] / 1_000_000
        + out * rates["output"] / 1_000_000
        + cache_rd * rates["cache_read"] / 1_000_000
        + cache_cr * rates["cache_create"] / 1_000_000
    )
    tokens = {
        "input": inp,
        "output": out,
        "cache_read": cache_rd,
        "cache_create": cache_cr,
    }
    return cost, tokens


def parse_timestamp_to_local_date(ts_str: str) -> datetime.date | None:
    """Parse ISO 8601 timestamp (with Z suffix) to local date."""
    try:
        dt = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.astimezone().date()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Session JSONL scanner
# ---------------------------------------------------------------------------

def find_session_files() -> list[str]:
    """Find all session JSONL files across all projects."""
    patterns = [
        str(PROJECTS_DIR / "*" / "*.jsonl"),
        str(PROJECTS_DIR / "*" / "*" / "subagents" / "*.jsonl"),
    ]
    files = []
    for pat in patterns:
        files.extend(glob.glob(pat))
    return files


def scan_cost_for_date_range(
    start_date: datetime.date,
    end_date: datetime.date,
    file_cache: dict | None = None,
) -> CostData:
    """Scan session files for cost data within a date range (inclusive)."""
    result = CostData()

    # Convert start_date to epoch for mtime filtering
    start_epoch = datetime.datetime.combine(
        start_date, datetime.time.min
    ).timestamp()

    for filepath in find_session_files():
        try:
            mtime = os.path.getmtime(filepath)
            if mtime < start_epoch:
                continue  # file hasn't been touched since start_date

            fsize = os.path.getsize(filepath)
            if file_cache is not None and filepath in file_cache:
                cached_size, cached_data = file_cache[filepath]
                if cached_size == fsize:
                    # File unchanged — use cached data
                    result.total_cost += cached_data.total_cost
                    result.message_count += cached_data.message_count
                    for fam, mc in cached_data.by_model.items():
                        if fam not in result.by_model:
                            result.by_model[fam] = ModelCost()
                        rm = result.by_model[fam]
                        rm.cost += mc.cost
                        rm.input_tokens += mc.input_tokens
                        rm.output_tokens += mc.output_tokens
                        rm.cache_read_tokens += mc.cache_read_tokens
                        rm.cache_create_tokens += mc.cache_create_tokens
                        rm.messages += mc.messages
                    continue

            # Parse this file fresh
            file_data = CostData()
            with open(filepath) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except Exception:
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
                        continue
                    if entry_date < start_date or entry_date > end_date:
                        continue

                    cost, tokens = compute_message_cost(usage, model)
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

            # Merge into result
            result.total_cost += file_data.total_cost
            result.message_count += file_data.message_count
            for fam, mc in file_data.by_model.items():
                if fam not in result.by_model:
                    result.by_model[fam] = ModelCost()
                rm = result.by_model[fam]
                rm.cost += mc.cost
                rm.input_tokens += mc.input_tokens
                rm.output_tokens += mc.output_tokens
                rm.cache_read_tokens += mc.cache_read_tokens
                rm.cache_create_tokens += mc.cache_create_tokens
                rm.messages += mc.messages

            # Cache this file's data
            if file_cache is not None:
                file_cache[filepath] = (fsize, file_data)

        except Exception:
            continue

    return result


# ---------------------------------------------------------------------------
# Billing period helpers
# ---------------------------------------------------------------------------

def billing_period_start(billing_day: int) -> datetime.date:
    today = datetime.date.today()
    if today.day >= billing_day:
        try:
            return datetime.date(today.year, today.month, billing_day)
        except ValueError:
            return datetime.date(today.year, today.month, 1)
    else:
        m = today.month - 1 or 12
        y = today.year if today.month > 1 else today.year - 1
        try:
            return datetime.date(y, m, billing_day)
        except ValueError:
            return datetime.date(y, m, 1)


def next_billing_reset(billing_day: int) -> datetime.datetime:
    today = datetime.date.today()
    year, month = today.year, today.month

    def make_date(y: int, m: int, d: int) -> datetime.date:
        last = calendar.monthrange(y, m)[1]
        return datetime.date(y, m, min(d, last))

    if today.day < billing_day:
        reset_date = make_date(year, month, billing_day)
    else:
        nm = month % 12 + 1
        ny = year + (1 if month == 12 else 0)
        reset_date = make_date(ny, nm, billing_day)

    return datetime.datetime.combine(reset_date, datetime.time.min)


def reset_countdown(billing_day: int) -> tuple[int, int, int]:
    delta = next_billing_reset(billing_day) - datetime.datetime.now()
    total = max(0, int(delta.total_seconds()))
    d = total // 86400
    h = (total % 86400) // 3600
    m = (total % 3600) // 60
    return d, h, m


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def make_bar(pct: float, width: int = 20) -> str:
    clamped = max(0, min(100, pct))
    filled = round(clamped / 100 * width)
    return "█" * filled + "░" * (width - filled)


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def fmt_cost(c: float) -> str:
    if c >= 100:
        return f"${c:.0f}"
    if c >= 10:
        return f"${c:.1f}"
    return f"${c:.2f}"


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def send_notification(title: str, message: str) -> None:
    subprocess.run(
        [
            "osascript", "-e",
            f'display notification "{message}" with title "{title}" sound name "Glass"',
        ],
        capture_output=True,
    )


def _read_lock(path: Path) -> str:
    if path.exists():
        return path.read_text().strip()
    return ""


def _write_lock(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(datetime.date.today().isoformat())


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class ClaudeUsageMonitor(rumps.App):
    def __init__(self) -> None:
        super().__init__("📊", quit_button=None)
        self.config = load_config()
        self._file_cache: dict = {}
        self._cache_date: datetime.date = datetime.date.today()

        # First-run wizard
        if not CONFIG_PATH.exists():
            self._first_run_setup()
            save_config(self.config)

        # Build menu
        self.menu = [
            rumps.MenuItem("daily_summary"),
            rumps.MenuItem("progress_bar"),
            rumps.separator,
            rumps.MenuItem("model_line_1"),
            rumps.MenuItem("model_line_2"),
            rumps.MenuItem("model_line_3"),
            rumps.separator,
            rumps.MenuItem("period_total"),
            rumps.MenuItem("billing_reset"),
            rumps.separator,
            rumps.MenuItem("Settings", callback=self.open_settings),
            rumps.MenuItem("Refresh Now", callback=self.on_refresh),
            rumps.separator,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]

        self._update()

        rumps.Timer(self._tick, REFRESH_INTERVAL_SEC).start()
        rumps.Timer(self._check_notifications, NOTIF_CHECK_INTERVAL_SEC).start()

    # ------------------------------------------------------------------
    # First-run setup
    # ------------------------------------------------------------------

    def _first_run_setup(self) -> None:
        resp = rumps.Window(
            message=(
                "Welcome to CredClaude!\n\n"
                "What day of the month does your Claude billing reset?\n"
                "(Enter 1–28, e.g. '1' for the 1st of each month)"
            ),
            title="CredClaude — Setup (1/2)",
            default_text="1",
            ok="Next",
            cancel="Skip",
        ).run()
        if resp.clicked and resp.text.strip().isdigit():
            val = int(resp.text.strip())
            if 1 <= val <= 28:
                self.config["billing_day"] = val

        resp2 = rumps.Window(
            message=(
                "What is your daily compute budget in USD?\n\n"
                "This is the API-equivalent cost that sets 100% on the bar.\n"
                "Cache + output tokens dominate cost.\n"
                "Light day: ~$20–50. Heavy agentic day: ~$80–150.\n"
                "Start with $100 and adjust after a few days."
            ),
            title="CredClaude — Setup (2/2)",
            default_text="100.00",
            ok="Done",
            cancel="Skip",
        ).run()
        if resp2.clicked:
            try:
                val2 = float(resp2.text.strip())
                if val2 > 0:
                    self.config["daily_budget_usd"] = val2
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def _invalidate_cache_if_new_day(self) -> None:
        today = datetime.date.today()
        if today != self._cache_date:
            self._file_cache.clear()
            self._cache_date = today

    # ------------------------------------------------------------------
    # Display update
    # ------------------------------------------------------------------

    def _update(self) -> None:
        cfg = self.config
        billing_day: int = cfg.get("billing_day", 1)
        budget: float = cfg.get("daily_budget_usd", 5.00)

        self._invalidate_cache_if_new_day()

        # Today's cost
        today = datetime.date.today()
        today_data = scan_cost_for_date_range(today, today, self._file_cache)

        # Billing period cost (no cache — different date range)
        period_start = billing_period_start(billing_day)
        period_data = scan_cost_for_date_range(period_start, today)

        pct = min(999, round(today_data.total_cost / budget * 100)) if budget > 0 else 0
        days, hours, minutes = reset_countdown(billing_day)

        # Title bar
        self.title = f"{fmt_cost(today_data.total_cost)} ({pct}%) | {days}d {hours}h"

        # Menu items
        self.menu["daily_summary"].title = (
            f"{fmt_cost(today_data.total_cost)} / {fmt_cost(budget)} today  ({pct}%)"
        )
        self.menu["progress_bar"].title = f"[{make_bar(pct)}]"

        # Model breakdown (up to 3 lines)
        model_lines = []
        for fam in ("opus", "sonnet", "haiku"):
            mc = today_data.by_model.get(fam)
            if mc and mc.cost > 0.001:
                tok_str = (
                    f"{fmt_tokens(mc.input_tokens)} in / "
                    f"{fmt_tokens(mc.output_tokens)} out"
                )
                model_lines.append(
                    f"{fam.title():8s} {fmt_cost(mc.cost):>7s}   "
                    f"({tok_str})"
                )

        for i, key in enumerate(["model_line_1", "model_line_2", "model_line_3"]):
            if i < len(model_lines):
                self.menu[key].title = model_lines[i]
            else:
                self.menu[key].title = ""

        # Period + reset
        period_days = (today - period_start).days + 1
        self.menu["period_total"].title = (
            f"Period total: {fmt_cost(period_data.total_cost)}  "
            f"({period_days} days)"
        )
        self.menu["billing_reset"].title = (
            f"Resets in {days}d {hours}h {minutes}m"
        )

        # Store today's cost for notification checks
        self._today_cost = today_data.total_cost

    # ------------------------------------------------------------------
    # Timer callbacks
    # ------------------------------------------------------------------

    def _tick(self, _sender) -> None:
        self.config = load_config()
        self._update()

    def _check_notifications(self, _sender) -> None:
        cfg = self.config
        if not cfg.get("notifications_enabled", True):
            return

        today = datetime.date.today()
        today_str = today.isoformat()

        # Billing reset notification
        billing_day: int = cfg.get("billing_day", 1)
        if today.day == billing_day:
            if _read_lock(NOTIF_LOCK_PATH) != today_str:
                send_notification(
                    "Claude Usage Reset",
                    "Your Claude usage limit has reset — fresh quota available!",
                )
                _write_lock(NOTIF_LOCK_PATH)

        # Budget warning notification
        budget = cfg.get("daily_budget_usd", 5.00)
        warn_pct = cfg.get("warn_at_pct", 80)
        cost = getattr(self, "_today_cost", 0)
        if budget > 0 and cost / budget * 100 >= warn_pct:
            warn_lock = APP_DIR / f".warn_{today_str}"
            if not warn_lock.exists():
                send_notification(
                    "Claude Budget Warning",
                    f"You've used {fmt_cost(cost)} of your {fmt_cost(budget)} daily budget ({round(cost/budget*100)}%).",
                )
                _write_lock(warn_lock)

    # ------------------------------------------------------------------
    # Menu callbacks
    # ------------------------------------------------------------------

    def on_refresh(self, _sender) -> None:
        self._file_cache.clear()
        self.config = load_config()
        self._update()

    def open_settings(self, _sender) -> None:
        cfg = self.config

        r1 = rumps.Window(
            message=(
                f"Current billing reset day: {cfg.get('billing_day', 1)}\n\n"
                "Enter new billing day (1–28):"
            ),
            title="Settings — Billing Day",
            default_text=str(cfg.get("billing_day", 1)),
            ok="Save",
            cancel="Cancel",
        ).run()
        if r1.clicked and r1.text.strip().isdigit():
            val = int(r1.text.strip())
            if 1 <= val <= 28:
                cfg["billing_day"] = val

        r2 = rumps.Window(
            message=(
                f"Current daily budget: ${cfg.get('daily_budget_usd', 100.00):.2f}\n\n"
                "Enter new daily budget in USD:"
            ),
            title="Settings — Daily Budget",
            default_text=f"{cfg.get('daily_budget_usd', 100.00):.2f}",
            ok="Save",
            cancel="Cancel",
        ).run()
        if r2.clicked:
            try:
                val2 = float(r2.text.strip())
                if val2 > 0:
                    cfg["daily_budget_usd"] = val2
            except ValueError:
                pass

        r3 = rumps.Window(
            message=(
                f"Current warning threshold: {cfg.get('warn_at_pct', 80)}%\n\n"
                "Notify when daily usage reaches this % of budget:"
            ),
            title="Settings — Warning Threshold",
            default_text=str(cfg.get("warn_at_pct", 80)),
            ok="Save",
            cancel="Cancel",
        ).run()
        if r3.clicked and r3.text.strip().isdigit():
            val3 = int(r3.text.strip())
            if 1 <= val3 <= 100:
                cfg["warn_at_pct"] = val3

        save_config(cfg)
        self.config = cfg
        self._file_cache.clear()
        self._update()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ClaudeUsageMonitor().run()
