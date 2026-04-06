"""CredClaude — macOS menu bar app (rumps UI layer).

Shows the current 5-hour session usage bar and reset time,
matching the claude.ai "Plan usage limits" display.
"""

from __future__ import annotations

import datetime
import logging
import time

import objc
import rumps
from AppKit import NSApplication, NSApplicationActivationPolicyAccessory, NSBundle, NSImage, NSObject
from Foundation import NSProcessInfo

from credclaude import __version__
from credclaude.auth_launcher import ReauthGate, launch_claude_auth_login
from credclaude.config import (
    APP_DIR,
    CONFIG_PATH,
    NOTIF_LOCK_PATH,
    NOTIF_CHECK_INTERVAL_SEC,
    REFRESH_INTERVAL_SEC,
    load_config,
    save_config,
)
from credclaude.keepalive import KeepaliveScheduler
from credclaude.limit_providers import CompositeLimitProvider
from credclaude.models import ProviderState
from credclaude.notifications import (
    cleanup_old_warn_locks,
    read_lock,
    send_notification,
    write_lock,
)
from credclaude.formatting import make_bar
from credclaude.icon_assets import menu_bar_icon_path, runtime_icon_path
from credclaude.time_utils import fmt_datetime as _fmt_datetime, fmt_relative as _fmt_relative

logger = logging.getLogger("credclaude.app")

# Minimum seconds between menu-open refreshes to avoid API spam
_MENU_OPEN_STALE_SEC = 30


class _MenuDelegate(NSObject):
    """NSMenu delegate that triggers a refresh when the menu opens."""

    app_ref = objc.ivar()

    def menuWillOpen_(self, menu):
        app = self.app_ref
        if app is None:
            return
        elapsed = time.monotonic() - app._last_refresh_time
        if elapsed >= _MENU_OPEN_STALE_SEC:
            app._refresh_now(None)


class CredClaude(rumps.App):
    def __init__(self) -> None:
        # Hide from Dock and app switcher — this is a menu-bar-only app
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        # Patch bundle name so Stage Manager/window tabs show "CredClaude" not "Python"
        _info = NSBundle.mainBundle().infoDictionary()
        if _info is not None:
            _info["CFBundleName"] = "CredClaude"
            _info["CFBundleDisplayName"] = "CredClaude"

        status_icon_path = menu_bar_icon_path()
        status_icon = str(status_icon_path) if status_icon_path is not None else None
        super().__init__("CredClaude", title=None, icon=status_icon, template=False, quit_button=None)

        # Set dock icon and process name (overrides Python defaults)
        icon_path = runtime_icon_path()
        if icon_path is not None:
            ns_icon = NSImage.alloc().initWithContentsOfFile_(str(icon_path))
            if ns_icon:
                NSApplication.sharedApplication().setApplicationIconImage_(ns_icon)
        NSProcessInfo.processInfo().setValue_forKey_("CredClaude", "processName")
        self.config = load_config()
        self._reauth_gate = ReauthGate(self._reauth_cooldown_sec())
        self._keepalive_scheduler = KeepaliveScheduler()

        # Limit provider (Official OAuth API + Estimator fallback)
        self._provider = CompositeLimitProvider(self.config)

        # Track last refresh time for menu-open staleness gate
        self._last_refresh_time = 0.0

        # Startup cleanup
        cleanup_old_warn_locks()

        # Info menu items (updated dynamically on each refresh)
        # Use a no-op callback so items appear enabled (not greyed out)
        _noop = lambda _: None
        self._plan_item = rumps.MenuItem("Plan: —", callback=_noop)
        self._weekly_bar_item = rumps.MenuItem("Weekly: —", callback=_noop)
        self._weekly_reset_item = rumps.MenuItem("  Resets: —", callback=_noop)
        self._extra_usage_item = rumps.MenuItem("Extra usage: —", callback=_noop)

        # Separator items we need to hide/show with their sections
        self._sep_after_plan = rumps.MenuItem("")
        self._sep_after_weekly = rumps.MenuItem("")
        self._sep_after_extra = rumps.MenuItem("")

        # Build menu — separators are managed manually via NSMenuItem
        self.menu = [
            self._plan_item,
            self._sep_after_plan,
            self._weekly_bar_item,
            self._weekly_reset_item,
            self._sep_after_weekly,
            self._extra_usage_item,
            self._sep_after_extra,
            rumps.MenuItem("Refresh", callback=self._refresh_now),
            rumps.MenuItem("Re-authenticate", callback=self._reauth_now),
            rumps.MenuItem("Settings", callback=self._show_settings),
            rumps.separator,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]

        # Replace placeholder items with real NSMenuItem separators
        for sep_item in (self._sep_after_plan, self._sep_after_weekly, self._sep_after_extra):
            ns = sep_item._menuitem
            ns_menu = ns.menu()
            if ns_menu:
                idx = ns_menu.indexOfItem_(ns)
                ns_menu.removeItemAtIndex_(idx)
                real_sep = __import__("AppKit").NSMenuItem.separatorItem()
                ns_menu.insertItem_atIndex_(real_sep, idx)
                sep_item._menuitem = real_sep

        # Start with info items hidden (shown once data arrives)
        self._set_info_hidden(plan=True, weekly=True, extra=True)

        # Set up menu delegate for click-to-refresh
        self._menu_delegate = _MenuDelegate.alloc().init()
        self._menu_delegate.app_ref = self
        # rumps wraps NSMenu — access the underlying Cocoa object
        ns_menu = getattr(self._menu, '_menu', None)
        if ns_menu is not None:
            ns_menu.setDelegate_(self._menu_delegate)

        self._startup_timer = rumps.Timer(self._startup_update, 5)
        self._startup_timer.start()

        # Auto-refresh timer (only starts if auto_refresh is enabled)
        refresh_sec = self.config.get("refresh_interval_sec", REFRESH_INTERVAL_SEC)
        self._tick_timer = rumps.Timer(self._tick, refresh_sec)
        if self.config.get("auto_refresh", True):
            self._tick_timer.start()

        rumps.Timer(self._check_notifications, NOTIF_CHECK_INTERVAL_SEC).start()
        logger.info("CredClaude started (v%s)", __version__)

    # ------------------------------------------------------------------
    # Info item visibility
    # ------------------------------------------------------------------
    def _set_info_hidden(self, plan: bool, weekly: bool, extra: bool) -> None:
        """Show/hide info sections and their separators.

        Separator logic avoids stacked/orphan separators:
        - sep_after_plan: shown only if plan is visible AND (weekly or extra visible)
        - sep_after_weekly: shown only if weekly is visible AND extra is visible
        - sep_after_extra: shown if ANY info item is visible (divides info from actions)
        """
        any_visible = not (plan and weekly and extra)

        self._plan_item._menuitem.setHidden_(plan)
        self._sep_after_plan._menuitem.setHidden_(plan or (weekly and extra))

        self._weekly_bar_item._menuitem.setHidden_(weekly)
        self._weekly_reset_item._menuitem.setHidden_(weekly)
        self._sep_after_weekly._menuitem.setHidden_(weekly or extra)

        self._extra_usage_item._menuitem.setHidden_(extra)
        self._sep_after_extra._menuitem.setHidden_(not any_visible)

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
        self._apply_limit(limit)

    def _apply_limit(self, limit) -> None:
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
        # Dropdown: Plan type (hidden when not available)
        # ------------------------------------------------------------------
        sub_type = limit.subscription_type
        show_plan = sub_type is not None
        if show_plan:
            self._plan_item.title = f"Plan: {sub_type.replace('_', ' ').title()}"

        # ------------------------------------------------------------------
        # Dropdown: Weekly limit bar + reset time (hidden when not applicable)
        # ------------------------------------------------------------------
        weekly_pct = limit.weekly_utilization_pct
        show_weekly = weekly_pct is not None
        if show_weekly:
            bar = make_bar(weekly_pct, width=15)
            self._weekly_bar_item.title = f"Weekly: {bar} {weekly_pct:.0f}%"
            self._weekly_reset_item.title = (
                f"  Resets: {_fmt_datetime(limit.weekly_resets_at)}"
            )

        # ------------------------------------------------------------------
        # Dropdown: Extra usage / credits (hidden when not enabled)
        # ------------------------------------------------------------------
        show_extra = limit.extra_usage_enabled is True
        if show_extra:
            if limit.extra_usage_utilization is not None:
                bar = make_bar(limit.extra_usage_utilization, width=15)
                self._extra_usage_item.title = (
                    f"Extra usage: {bar} {limit.extra_usage_utilization:.0f}%"
                )
            elif (limit.extra_usage_used is not None
                  and limit.extra_usage_monthly_limit is not None):
                self._extra_usage_item.title = (
                    f"Extra usage: ${limit.extra_usage_used:.2f}"
                    f" / ${limit.extra_usage_monthly_limit:.2f}"
                )
            else:
                self._extra_usage_item.title = "Extra usage: enabled"

        self._set_info_hidden(
            plan=not show_plan,
            weekly=not show_weekly,
            extra=not show_extra,
        )

        # Store for notification checks
        self._last_pct = pct
        self._last_limit = limit
        self._last_refresh_time = time.monotonic()
        self._maybe_auto_reauth(limit)
        self._maybe_schedule_keepalive(limit)

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
        """Poll at the configured interval."""
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
        if _sender is not None:
            limit = self._provider.force_refresh()
            self._apply_limit(limit)
            return
        self._update()

    def _reauth_now(self, _sender) -> None:
        self.config = load_config()
        self._reauth_gate.update_cooldown(self._reauth_cooldown_sec())
        self._trigger_reauth(auto=False, reason="manual menu action")

    def _show_settings(self, _sender) -> None:
        from credclaude.settings import SettingsWindow
        last = getattr(self, "_last_limit", None)
        data_source = "OAuth (Live)"
        if last is not None:
            src = last.source or ""
            if "unavailable" in src:
                data_source = "OAuth (Unavailable)"
            elif "estimated" in src:
                data_source = "Estimated"
        SettingsWindow.show(self.config, self._on_settings_saved, data_source=data_source)

    def _on_settings_saved(self, cfg: dict) -> None:
        old_interval = self.config.get("refresh_interval_sec", REFRESH_INTERVAL_SEC)
        old_auto = self.config.get("auto_refresh", True)
        self.config = cfg
        self._provider.update_config(cfg)
        self._reauth_gate.update_cooldown(self._reauth_cooldown_sec())

        new_interval = cfg.get("refresh_interval_sec", REFRESH_INTERVAL_SEC)
        new_auto = cfg.get("auto_refresh", True)

        # Handle auto-refresh toggle and interval changes
        if new_auto:
            if not old_auto or new_interval != old_interval:
                self._tick_timer.stop()
                self._tick_timer = rumps.Timer(self._tick, new_interval)
                self._tick_timer.start()
                logger.info("Auto-refresh ON, interval %ds", new_interval)
            if not old_auto:
                # Trigger an immediate refresh when re-enabling
                self._update()
        else:
            if old_auto:
                self._tick_timer.stop()
                logger.info("Auto-refresh OFF")

        last_limit = getattr(self, "_last_limit", None)
        if not cfg.get("keepalive_enabled", False):
            self._keepalive_scheduler.cancel()
        elif last_limit is not None and last_limit.resets_at is not None:
            self._keepalive_scheduler.schedule(last_limit.resets_at)

        logger.info("Settings applied")

    def _reauth_cooldown_sec(self) -> int:
        """Return configured auto re-auth cooldown in seconds."""
        raw = self.config.get("auto_reauth_cooldown_sec", 1800)
        try:
            val = int(raw)
        except Exception:
            val = 1800
        return max(30, min(86400, val))

    def _maybe_auto_reauth(self, limit) -> None:
        """Trigger background re-auth flow when auth expiry is detected."""
        if not self.config.get("auto_reauth_enabled", True):
            return
        self._reauth_gate.update_cooldown(self._reauth_cooldown_sec())
        if not self._reauth_gate.eligible_for_auto_launch(limit.error):
            return
        self._trigger_reauth(auto=True, reason=limit.error or "auth issue")

    def _maybe_schedule_keepalive(self, limit) -> None:
        """Schedule or cancel the post-reset keepalive ping."""
        if not self.config.get("keepalive_enabled", False):
            self._keepalive_scheduler.cancel()
            return
        if limit.resets_at is not None:
            self._keepalive_scheduler.schedule(limit.resets_at)

    def _trigger_reauth(self, auto: bool, reason: str) -> None:
        """Launch `claude auth login` in Terminal and surface feedback."""
        self._reauth_gate.mark_attempt()
        mode = "auto" if auto else "manual"
        logger.info("Starting %s re-auth flow (%s)", mode, reason)
        result = launch_claude_auth_login()
        if result.success:
            logger.info("Re-auth launch succeeded (%s)", mode)
            send_notification(
                "CredClaude Re-authenticate",
                "Terminal opened for Claude login. Approve in browser, then refresh.",
            )
            return

        logger.warning("Re-auth launch failed (%s): %s", mode, result.message)
        send_notification("CredClaude Re-authenticate Failed", result.message)
