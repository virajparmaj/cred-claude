"""CredClaude — macOS menu bar app (rumps UI layer).

Shows the current 5-hour session usage bar and reset time,
matching the claude.ai "Plan usage limits" display.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

import rumps

_ICON_PATH = Path(__file__).parent.parent / "claude_monitor_logo.png"

from credclaude import __version__
from credclaude.billing import reset_countdown
from credclaude.config import (
    APP_DIR,
    CONFIG_PATH,
    NOTIF_LOCK_PATH,
    NOTIF_CHECK_INTERVAL_SEC,
    REFRESH_INTERVAL_SEC,
    load_config,
    save_config,
)
from credclaude.formatting import make_bar
from credclaude.limit_providers import CompositeLimitProvider
from credclaude.notifications import (
    cleanup_old_warn_locks,
    read_lock,
    send_notification,
    write_lock,
)

logger = logging.getLogger("credclaude.app")

PLAN_TIER_OPTIONS = {
    "pro": "Pro ($20/mo)",
    "max_5x": "Max 5x ($100/mo)",
    "max_20x": "Max 20x ($200/mo)",
}


def _fmt_relative(dt: datetime.datetime | None) -> str:
    """Format a future datetime as 'Xh Ym' countdown."""
    if dt is None:
        return "--"
    now = datetime.datetime.now().astimezone()
    if dt.tzinfo is None:
        dt = dt.astimezone()
    delta = dt - now
    total_sec = max(0, int(delta.total_seconds()))
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    if h == 0:
        return f"{m}m"
    return f"{h}h {m}m"


def _fmt_last_sync(dt: datetime.datetime | None) -> str:
    """Format last sync time as relative string."""
    if dt is None:
        return "never"
    now = datetime.datetime.now().astimezone()
    if dt.tzinfo is None:
        dt = dt.astimezone()
    diff = (now - dt).total_seconds()
    if diff < 60:
        return "just now"
    if diff < 3600:
        return f"{int(diff // 60)} min ago"
    return dt.strftime("%H:%M")


class CredClaude(rumps.App):
    def __init__(self) -> None:
        icon = str(_ICON_PATH) if _ICON_PATH.exists() else None
        super().__init__("CredClaude", title=None, icon=icon, template=False, quit_button=None)
        self.config = load_config()

        # Limit provider (Official OAuth API + Estimator fallback)
        self._provider = CompositeLimitProvider(self.config)

        # First-run wizard if no config exists yet
        if not CONFIG_PATH.exists():
            self._first_run_setup()
            save_config(self.config)

        # Startup cleanup
        cleanup_old_warn_locks()

        self._last_manual_refresh: datetime.datetime | None = None

        # Build simplified menu
        self.menu = [
            rumps.MenuItem("session_bar"),
            rumps.MenuItem("session_reset"),
            rumps.MenuItem("billing_reset"),
            rumps.separator,
            rumps.MenuItem("source_info"),
            rumps.MenuItem("last_refresh"),
            rumps.MenuItem("auth_help"),
            rumps.MenuItem("weekly_cap"),
            rumps.separator,
            rumps.MenuItem("Settings", callback=self.open_settings),
            rumps.MenuItem("Refresh Now", callback=self.on_refresh),
            rumps.separator,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]

        self._startup_timer = rumps.Timer(self._startup_update, 5)
        self._startup_timer.start()

        rumps.Timer(self._tick, REFRESH_INTERVAL_SEC).start()
        rumps.Timer(self._check_notifications, NOTIF_CHECK_INTERVAL_SEC).start()
        logger.info("CredClaude started (v%s)", __version__)

    # ------------------------------------------------------------------
    # First-run setup
    # ------------------------------------------------------------------
    def _first_run_setup(self) -> None:
        r = rumps.Window(
            message=(
                "Welcome to CredClaude!\n\n"
                "What Claude Code plan are you on?\n"
                "Enter: pro, max_5x, or max_20x"
            ),
            title="CredClaude — Setup",
            default_text="pro",
            ok="Done",
            cancel="Skip",
        ).run()
        if r.clicked and r.text.strip().lower() in ("pro", "max_5x", "max_20x"):
            self.config["plan_tier"] = r.text.strip().lower()

    # ------------------------------------------------------------------
    # Display update
    # ------------------------------------------------------------------
    def _update(self) -> None:
        try:
            self._do_update()
        except Exception as e:
            logger.error("Update cycle failed: %s", e, exc_info=True)
            self.title = "⚠ err"

    def _do_update(self) -> None:
        limit = self._provider.get_limit_info()
        pct = limit.utilization_pct
        resets_at = limit.resets_at

        # Pre-compute countdown once
        countdown = _fmt_relative(resets_at) if resets_at is not None else None

        # ------------------------------------------------------------------
        # Title bar — always clean, no stale markers
        # ------------------------------------------------------------------
        if pct is not None and countdown is not None:
            self.title = f"{pct:.0f}% | {countdown}"
        elif pct is not None:
            self.title = f"{pct:.0f}%"
        else:
            self.title = "⏸ --"

        # ------------------------------------------------------------------
        # Session bar
        # ------------------------------------------------------------------
        if pct is not None:
            bar = make_bar(pct)
            self.menu["session_bar"].title = f"[{bar}]  {pct:.0f}% used"
        else:
            self.menu["session_bar"].title = "Loading..."

        # ------------------------------------------------------------------
        # Reset time
        # ------------------------------------------------------------------
        if pct is not None and countdown is not None:
            self.menu["session_reset"].title = f"Resets in {countdown}"
        else:
            self.menu["session_reset"].title = ""

        # ------------------------------------------------------------------
        # Source + last refresh
        # ------------------------------------------------------------------
        if pct is not None:
            self.menu["source_info"].title = f"Source: {limit.source}"
        else:
            self.menu["source_info"].title = ""

        if limit.last_sync:
            self.menu["last_refresh"].title = f"Last updated: {_fmt_last_sync(limit.last_sync)}"
        elif pct is None:
            self.menu["last_refresh"].title = ""
        else:
            self.menu["last_refresh"].title = f"Last updated: {_fmt_last_sync(limit.last_sync)}"

        # Auth help — show actionable guidance when token is expired
        err = limit.error or ""
        if "Token expired" in err or "Unauthorized" in err or "401" in err:
            self.menu["auth_help"].title = "Fix: Run 'claude auth login' in terminal"
        else:
            self.menu["auth_help"].title = ""

        # ------------------------------------------------------------------
        # Billing reset countdown
        # ------------------------------------------------------------------
        billing_day = self.config.get("billing_day", 1)
        days, hours, mins = reset_countdown(billing_day)
        if days > 0:
            self.menu["billing_reset"].title = f"Billing resets in {days}d {hours}h"
        else:
            self.menu["billing_reset"].title = f"Billing resets in {hours}h {mins}m"

        # ------------------------------------------------------------------
        # Weekly cap note
        # ------------------------------------------------------------------
        cap_note = getattr(limit, "weekly_cap_note", "") or ""
        self.menu["weekly_cap"].title = cap_note if cap_note else ""

        # Store for notification checks
        self._last_pct = pct
        self._last_limit = limit

    # ------------------------------------------------------------------
    # Timer callbacks
    # ------------------------------------------------------------------
    def _startup_update(self, sender) -> None:
        """Delayed first update — uses snapshot if fresh, else hits API."""
        sender.stop()
        if self._provider.try_snapshot_startup():
            # Snapshot seeded the cache — display it immediately
            self._update()
            logger.info("Startup: using snapshot, next API call in %ds", REFRESH_INTERVAL_SEC)
            return
        # No usable snapshot — fetch from API
        self._update()

    def _tick(self, _sender) -> None:
        """Poll every 60 seconds — no adaptive gating."""
        self.config = load_config()
        self._provider.update_config(self.config)
        self._update()

    def _check_notifications(self, _sender) -> None:
        cfg = self.config
        if not cfg.get("notifications_enabled", True):
            return

        today_str = datetime.date.today().isoformat()
        pct = getattr(self, "_last_pct", None)
        warn_pct = cfg.get("warn_at_pct", 80)

        # High usage warning
        if pct is not None and pct >= warn_pct:
            warn_lock = APP_DIR / f".warn_{today_str}"
            if not warn_lock.exists():
                countdown = "--"
                limit = getattr(self, "_last_limit", None)
                if limit and limit.resets_at:
                    countdown = _fmt_relative(limit.resets_at)
                send_notification(
                    "Claude Session Limit Warning",
                    f"You've used {pct:.0f}% of your session. Resets in {countdown}.",
                )
                write_lock(warn_lock)

        # Billing day notification (kept for users who care about billing cycle)
        billing_day: int = cfg.get("billing_day", 1)
        today = datetime.date.today()
        if today.day == billing_day:
            if read_lock(NOTIF_LOCK_PATH) != today_str:
                send_notification(
                    "Claude Billing Cycle Reset",
                    "Your Claude billing period has reset.",
                )
                write_lock(NOTIF_LOCK_PATH)

    # ------------------------------------------------------------------
    # Menu callbacks
    # ------------------------------------------------------------------
    def on_refresh(self, _sender) -> None:
        now = datetime.datetime.now()
        if self._last_manual_refresh and (now - self._last_manual_refresh).total_seconds() < 30:
            logger.debug("Manual refresh throttled (< 30s since last)")
            return
        self._last_manual_refresh = now
        self.config = load_config()
        self._provider.update_config(self.config)
        self._provider.force_refresh()
        self._update()
        logger.info("Manual refresh triggered")

    def open_settings(self, _sender) -> None:
        cfg = self.config

        # Plan tier (only shown if official API fails)
        current_tier = cfg.get("plan_tier", "pro")
        r0 = rumps.Window(
            message=(
                f"Current plan: {PLAN_TIER_OPTIONS.get(current_tier, current_tier)}\n\n"
                "Enter plan tier (used as fallback when API is unavailable):\n"
                "pro, max_5x, or max_20x"
            ),
            title="Settings — Plan Tier",
            default_text=current_tier,
            ok="Save",
            cancel="Cancel",
        ).run()
        if r0.clicked and r0.text.strip().lower() in ("pro", "max_5x", "max_20x"):
            cfg["plan_tier"] = r0.text.strip().lower()

        # Warning threshold
        r1 = rumps.Window(
            message=(
                f"Current warning threshold: {cfg.get('warn_at_pct', 80)}%\n\n"
                "Notify when session usage reaches this %:"
            ),
            title="Settings — Warning Threshold",
            default_text=str(cfg.get("warn_at_pct", 80)),
            ok="Save",
            cancel="Cancel",
        ).run()
        if r1.clicked and r1.text.strip().isdigit():
            val = int(r1.text.strip())
            if 1 <= val <= 100:
                cfg["warn_at_pct"] = val

        # Notifications toggle
        notif_on = cfg.get("notifications_enabled", True)
        r2 = rumps.Window(
            message=(
                f"Notifications currently: {'ON' if notif_on else 'OFF'}\n\n"
                "Enter 'on' or 'off':"
            ),
            title="Settings — Notifications",
            default_text="on" if notif_on else "off",
            ok="Save",
            cancel="Cancel",
        ).run()
        if r2.clicked:
            text = r2.text.strip().lower()
            if text in ("on", "yes", "true", "1"):
                cfg["notifications_enabled"] = True
            elif text in ("off", "no", "false", "0"):
                cfg["notifications_enabled"] = False

        save_config(cfg)
        self.config = cfg
        self._provider.update_config(cfg)
        logger.info("Settings updated")
