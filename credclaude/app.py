"""CredClaude — macOS menu bar app (rumps UI layer).

Shows the current 5-hour session usage bar and reset time,
matching the claude.ai "Plan usage limits" display.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

import rumps
from AppKit import NSApplication, NSImage
from Foundation import NSProcessInfo

_ICON_PATH = Path(__file__).parent.parent / "claude_monitor_logo.png"

from credclaude import __version__
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
from credclaude.models import ProviderState
from credclaude.notifications import (
    cleanup_old_warn_locks,
    read_lock,
    send_notification,
    write_lock,
)

logger = logging.getLogger("credclaude.app")


def _error_label(limit) -> str:
    """Return a short user-facing string explaining why data is unavailable."""
    if limit.error:
        snippet = limit.error[:40]
        return f"⚠ {snippet}"
    if limit.state == ProviderState.OFFLINE:
        return "⚠ Offline — check network"
    if limit.state == ProviderState.STALE:
        return "⚠ Stale data — retrying…"
    return "Loading…"


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


class CredClaude(rumps.App):
    def __init__(self) -> None:
        icon = str(_ICON_PATH) if _ICON_PATH.exists() else None
        super().__init__("CredClaude", title=None, icon=icon, template=False, quit_button=None)

        # Set dock icon and process name (overrides Python defaults)
        if _ICON_PATH.exists():
            ns_icon = NSImage.alloc().initWithContentsOfFile_(str(_ICON_PATH))
            if ns_icon:
                NSApplication.sharedApplication().setApplicationIconImage_(ns_icon)
        NSProcessInfo.processInfo().setValue_forKey_("CredClaude", "processName")
        self.config = load_config()

        # Limit provider (Official OAuth API + Estimator fallback)
        self._provider = CompositeLimitProvider(self.config)

        # First-run wizard if no config exists yet
        if not CONFIG_PATH.exists():
            self._first_run_setup()
            save_config(self.config)

        # Startup cleanup
        cleanup_old_warn_locks()

        # Build menu
        self.menu = [
            rumps.MenuItem("session_bar"),
            rumps.separator,
            rumps.MenuItem("Refresh", callback=self._refresh_now),
            rumps.MenuItem("Preferences...", callback=self._show_preferences),
            rumps.separator,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]

        self._startup_timer = rumps.Timer(self._startup_update, 5)
        self._startup_timer.start()

        refresh_sec = self.config.get("refresh_interval_sec", REFRESH_INTERVAL_SEC)
        self._tick_timer = rumps.Timer(self._tick, refresh_sec)
        self._tick_timer.start()
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
            err = limit.error or ""
            if any(w in err.lower() for w in ("token", "auth", "401", "unauthorized")):
                self.title = "⚠ auth"
            elif limit.state == ProviderState.OFFLINE:
                self.title = "⏸ off"
            else:
                self.title = "⏸ --"

        # ------------------------------------------------------------------
        # Session bar
        # ------------------------------------------------------------------
        if pct is not None:
            bar = make_bar(pct)
            self.menu["session_bar"].title = f"[{bar}]  {pct:.0f}% used"
        else:
            self.menu["session_bar"].title = _error_label(limit)

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
    def _refresh_now(self, _sender) -> None:
        self.config = load_config()
        self._provider.update_config(self.config)
        self._update()

    def _show_preferences(self, _sender) -> None:
        from credclaude.preferences import PreferencesWindow
        PreferencesWindow.show(self.config, self._on_preferences_saved)

    def _on_preferences_saved(self, cfg: dict) -> None:
        old_interval = self.config.get("refresh_interval_sec", REFRESH_INTERVAL_SEC)
        self.config = cfg
        self._provider.update_config(cfg)

        new_interval = cfg.get("refresh_interval_sec", REFRESH_INTERVAL_SEC)
        if new_interval != old_interval:
            self._tick_timer.stop()
            self._tick_timer = rumps.Timer(self._tick, new_interval)
            self._tick_timer.start()
            logger.info("Refresh interval changed to %ds", new_interval)

        logger.info("Preferences applied")
