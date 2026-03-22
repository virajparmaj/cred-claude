"""Native macOS settings window for CredClaude."""

from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path
from typing import Callable

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSButton,
    NSCenterTextAlignment,
    NSClosableWindowMask,
    NSColor,
    NSFont,
    NSImage,
    NSLeftTextAlignment,
    NSMakeRect,
    NSMiniaturizableWindowMask,
    NSObject,
    NSPopUpButton,
    NSSwitch,
    NSTextField,
    NSTitledWindowMask,
    NSView,
    NSWindow,
    NSWorkspace,
)

from credclaude import __version__
from credclaude.config import load_config, save_config, REFRESH_INTERVAL_SEC, LOG_PATH

logger = logging.getLogger("credclaude.settings")

_REPO_DIR = Path(__file__).parent.parent
_INSTALL_SCRIPT = _REPO_DIR / "install.sh"
_ICON_PATH = _REPO_DIR / "claude_monitor_logo.png"

PLAN_TIERS = [
    ("pro", "Pro ($20/mo)"),
    ("max_5x", "Max 5x ($100/mo)"),
    ("max_20x", "Max 20x ($200/mo)"),
]

_W = 460
_H = 444
_PAD = 24
_INNER = 18


def _label(text: str, x: float, y: float, w: float = 220, h: float = 20,
           bold: bool = False, size: float = 13, color: object = None) -> NSTextField:
    lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    lbl.setStringValue_(text)
    lbl.setBezeled_(False)
    lbl.setDrawsBackground_(False)
    lbl.setEditable_(False)
    lbl.setSelectable_(False)
    lbl.setAlignment_(NSLeftTextAlignment)
    lbl.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
    if color:
        lbl.setTextColor_(color)
    return lbl


def _input_field(x: float, y: float, w: float = 60, h: float = 22) -> NSTextField:
    f = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    f.setFont_(NSFont.systemFontOfSize_(13))
    return f


def _section_box(y: float, h: float) -> NSView:
    box = NSView.alloc().initWithFrame_(NSMakeRect(_PAD, y, _W - 2 * _PAD, h))
    box.setWantsLayer_(True)
    box.layer().setBackgroundColor_(NSColor.controlBackgroundColor().CGColor())
    box.layer().setCornerRadius_(10)
    box.layer().setBorderColor_(NSColor.separatorColor().CGColor())
    box.layer().setBorderWidth_(0.5)
    return box


class _FieldDelegate(NSObject):
    """Text field delegate for live validation feedback."""

    settings_window = objc.ivar()

    def controlTextDidChange_(self, notification):
        sw = self.settings_window
        if sw:
            sw._validate_fields()


class _Delegate(NSObject):
    """Window delegate + button action handler."""

    settings_window = objc.ivar()

    def windowWillClose_(self, notification):
        sw = self.settings_window
        if sw:
            sw._save_and_close()

    def onUpdate_(self, sender):
        sw = self.settings_window
        if sw:
            sw._run_update()

    def onViewLogs_(self, sender):
        sw = self.settings_window
        if sw:
            sw._open_logs()

    def onAutoRefreshToggle_(self, sender):
        sw = self.settings_window
        if sw:
            enabled = bool(sender.state())
            sw._refresh_field.setHidden_(not enabled)
            sw._refresh_suffix.setHidden_(not enabled)
            sw._refresh_helper.setHidden_(enabled)
            sw._refresh_field.setEditable_(enabled)
            sw._refresh_field.setEnabled_(enabled)

    def onAlertsToggle_(self, sender):
        sw = self.settings_window
        if sw:
            enabled = bool(sender.state())
            sw._threshold_field.setEditable_(enabled)
            sw._threshold_field.setEnabled_(enabled)
            sw._threshold_field.setAlphaValue_(1.0 if enabled else 0.4)
            sw._threshold_label.setTextColor_(
                None if enabled else NSColor.tertiaryLabelColor()
            )
            sw._threshold_suffix.setTextColor_(
                NSColor.secondaryLabelColor() if enabled else NSColor.tertiaryLabelColor()
            )

    def finishUpdate_(self, info):
        sw = self.settings_window
        if sw:
            success = info["success"]
            error = info.get("error", "")
            sw._updating = False
            sw._update_btn.setEnabled_(True)
            sw._update_btn.setTitle_("Check for Updates")
            if success:
                sw._update_status.setTextColor_(NSColor.systemGreenColor())
                sw._update_status.setStringValue_("CredClaude is up to date.")
            else:
                sw._update_status.setTextColor_(NSColor.systemRedColor())
                sw._update_status.setStringValue_(f"Update failed: {error[:50]}")


class SettingsWindow:
    """Singleton native settings window."""

    _instance: SettingsWindow | None = None

    def __init__(self, config: dict, on_save: Callable[[dict], None]) -> None:
        self._config = config.copy()
        self._on_save = on_save
        self._updating = False

    @classmethod
    def show(cls, config: dict, on_save: Callable[[dict], None]) -> None:
        if cls._instance is not None:
            cls._instance._window.makeKeyAndOrderFront_(None)
            return
        inst = cls(config, on_save)
        cls._instance = inst
        inst._build()
        inst._window.center()
        inst._window.makeKeyAndOrderFront_(None)

    def _build(self) -> None:
        style = NSTitledWindowMask | NSClosableWindowMask | NSMiniaturizableWindowMask
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, _W, _H), style, NSBackingStoreBuffered, False
        )
        self._window.setTitle_("CredClaude Settings")
        self._window.setReleasedWhenClosed_(False)

        # Set window icon (fixes Python icon in Stage Manager / Mission Control)
        if _ICON_PATH.exists():
            ns_icon = NSImage.alloc().initWithContentsOfFile_(str(_ICON_PATH))
            if ns_icon:
                self._window.setMiniwindowImage_(ns_icon)

        self._delegate = _Delegate.alloc().init()
        self._delegate.settings_window = self
        self._window.setDelegate_(self._delegate)

        # Field delegate for live validation
        self._field_delegate = _FieldDelegate.alloc().init()
        self._field_delegate.settings_window = self

        content = self._window.contentView()
        box_w = _W - 2 * _PAD
        y = _H - 50

        # =================================================================
        # Monitoring
        # =================================================================
        content.addSubview_(_label("Monitoring", _PAD, y, bold=True, size=14))
        y -= 8
        box_h = 100
        box = _section_box(y - box_h, box_h)
        content.addSubview_(box)

        # Plan tier
        ry = box_h - 30
        box.addSubview_(_label("Plan tier", _INNER, ry))
        self._tier_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(box_w - _INNER - 165, ry - 2, 165, 25), False
        )
        current_tier = self._config.get("plan_tier", "pro")
        for key, display in PLAN_TIERS:
            self._tier_popup.addItemWithTitle_(display)
            if key == current_tier:
                self._tier_popup.selectItemWithTitle_(display)
        box.addSubview_(self._tier_popup)

        # Refresh automatically
        ry -= 32
        box.addSubview_(_label("Refresh automatically", _INNER, ry))
        self._auto_refresh_switch = NSSwitch.alloc().initWithFrame_(
            NSMakeRect(box_w - _INNER - 40, ry, 40, 22)
        )
        auto_refresh_on = self._config.get("auto_refresh", True)
        self._auto_refresh_switch.setState_(1 if auto_refresh_on else 0)
        self._auto_refresh_switch.setTarget_(self._delegate)
        self._auto_refresh_switch.setAction_(
            objc.selector(self._delegate.onAutoRefreshToggle_, signature=b"v@:@")
        )
        box.addSubview_(self._auto_refresh_switch)

        # Refresh every
        ry -= 32
        box.addSubview_(_label("Refresh every", _INNER, ry))
        self._refresh_field = _input_field(box_w - _INNER - 110, ry, 55)
        self._refresh_field.setStringValue_(
            str(self._config.get("refresh_interval_sec", REFRESH_INTERVAL_SEC))
        )
        self._refresh_field.setEditable_(auto_refresh_on)
        self._refresh_field.setEnabled_(auto_refresh_on)
        self._refresh_field.setDelegate_(self._field_delegate)
        self._refresh_field.setHidden_(not auto_refresh_on)
        box.addSubview_(self._refresh_field)
        self._refresh_suffix = _label(
            "seconds", box_w - _INNER - 52, ry + 2, w=50, size=11,
            color=NSColor.secondaryLabelColor()
        )
        self._refresh_suffix.setHidden_(not auto_refresh_on)
        box.addSubview_(self._refresh_suffix)

        # Helper text shown when auto-refresh is OFF
        self._refresh_helper = _label(
            "Use menu bar Refresh action", box_w - _INNER - 210, ry, w=210, size=11,
            color=NSColor.tertiaryLabelColor()
        )
        self._refresh_helper.setHidden_(auto_refresh_on)
        box.addSubview_(self._refresh_helper)

        # Validation hint for refresh interval
        self._refresh_hint = _label(
            "", _INNER, ry - 16, w=box_w - 2 * _INNER, h=14, size=10,
            color=NSColor.systemRedColor()
        )
        self._refresh_hint.setHidden_(True)
        box.addSubview_(self._refresh_hint)

        y -= box_h + 26

        # =================================================================
        # Alerts
        # =================================================================
        content.addSubview_(_label("Alerts", _PAD, y, bold=True, size=14))
        y -= 8
        box_h = 68
        box = _section_box(y - box_h, box_h)
        content.addSubview_(box)

        # Usage alerts toggle
        ry = box_h - 30
        box.addSubview_(_label("Usage alerts", _INNER, ry))
        self._notif_switch = NSSwitch.alloc().initWithFrame_(
            NSMakeRect(box_w - _INNER - 40, ry, 40, 22)
        )
        alerts_on = self._config.get("notifications_enabled", True)
        self._notif_switch.setState_(1 if alerts_on else 0)
        self._notif_switch.setTarget_(self._delegate)
        self._notif_switch.setAction_(
            objc.selector(self._delegate.onAlertsToggle_, signature=b"v@:@")
        )
        box.addSubview_(self._notif_switch)

        # Alert threshold
        ry -= 32
        self._threshold_label = _label("Alert threshold", _INNER, ry)
        if not alerts_on:
            self._threshold_label.setTextColor_(NSColor.tertiaryLabelColor())
        box.addSubview_(self._threshold_label)
        self._threshold_field = _input_field(box_w - _INNER - 80, ry, 40)
        self._threshold_field.setStringValue_(str(self._config.get("warn_at_pct", 80)))
        self._threshold_field.setEditable_(alerts_on)
        self._threshold_field.setEnabled_(alerts_on)
        self._threshold_field.setAlphaValue_(1.0 if alerts_on else 0.4)
        self._threshold_field.setDelegate_(self._field_delegate)
        box.addSubview_(self._threshold_field)
        self._threshold_suffix = _label(
            "%", box_w - _INNER - 35, ry + 2, w=20, size=11,
            color=NSColor.secondaryLabelColor() if alerts_on else NSColor.tertiaryLabelColor()
        )
        box.addSubview_(self._threshold_suffix)

        # Validation hint for threshold
        self._threshold_hint = _label(
            "", _INNER, ry - 16, w=box_w - 2 * _INNER, h=14, size=10,
            color=NSColor.systemRedColor()
        )
        self._threshold_hint.setHidden_(True)
        box.addSubview_(self._threshold_hint)

        y -= box_h + 26

        # =================================================================
        # Support
        # =================================================================
        content.addSubview_(_label("Support", _PAD, y, bold=True, size=14))
        y -= 8
        box_h = 58
        box = _section_box(y - box_h, box_h)
        content.addSubview_(box)

        # Version + Check for Updates
        ry = box_h - 24
        self._version_label = _label(f"Version {__version__}", _INNER, ry)
        box.addSubview_(self._version_label)

        self._update_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(box_w - _INNER - 150, ry - 3, 150, 25)
        )
        self._update_btn.setTitle_("Check for Updates")
        self._update_btn.setBezelStyle_(NSBezelStyleRounded)
        self._update_btn.setTarget_(self._delegate)
        self._update_btn.setAction_(objc.selector(self._delegate.onUpdate_, signature=b"v@:@"))
        box.addSubview_(self._update_btn)

        # Status text + View Logs
        ry -= 24
        self._update_status = _label("", _INNER, ry, w=180, h=15, size=11,
                                      color=NSColor.secondaryLabelColor())
        box.addSubview_(self._update_status)

        self._logs_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(box_w - _INNER - 90, ry - 2, 90, 22)
        )
        self._logs_btn.setTitle_("View Logs")
        self._logs_btn.setBezelStyle_(NSBezelStyleRounded)
        self._logs_btn.setTarget_(self._delegate)
        self._logs_btn.setAction_(objc.selector(self._delegate.onViewLogs_, signature=b"v@:@"))
        box.addSubview_(self._logs_btn)

        # =================================================================
        # Footer
        # =================================================================
        footer = _label(
            "Settings are saved when this window is closed",
            0, 12, w=_W, h=16, size=11,
            color=NSColor.tertiaryLabelColor()
        )
        footer.setAlignment_(NSCenterTextAlignment)
        content.addSubview_(footer)

    def _validate_fields(self) -> None:
        """Live validation feedback for numeric input fields."""
        # Refresh interval validation
        raw = str(self._refresh_field.stringValue()).strip()
        if raw:
            try:
                val = int(raw)
                if val < 10:
                    self._refresh_hint.setStringValue_("Minimum is 10 seconds")
                    self._refresh_hint.setHidden_(False)
                    self._refresh_field.setTextColor_(NSColor.systemRedColor())
                elif val > 3600:
                    self._refresh_hint.setStringValue_("Maximum is 3600 seconds")
                    self._refresh_hint.setHidden_(False)
                    self._refresh_field.setTextColor_(NSColor.systemRedColor())
                else:
                    self._refresh_hint.setHidden_(True)
                    self._refresh_field.setTextColor_(NSColor.controlTextColor())
            except ValueError:
                self._refresh_hint.setStringValue_("Enter a number")
                self._refresh_hint.setHidden_(False)
                self._refresh_field.setTextColor_(NSColor.systemRedColor())
        else:
            self._refresh_hint.setHidden_(True)
            self._refresh_field.setTextColor_(NSColor.controlTextColor())

        # Threshold validation
        raw = str(self._threshold_field.stringValue()).strip()
        if raw:
            try:
                val = int(raw)
                if val < 1 or val > 100:
                    self._threshold_hint.setStringValue_("Enter 1\u2013100")
                    self._threshold_hint.setHidden_(False)
                    self._threshold_field.setTextColor_(NSColor.systemRedColor())
                else:
                    self._threshold_hint.setHidden_(True)
                    self._threshold_field.setTextColor_(NSColor.controlTextColor())
            except ValueError:
                self._threshold_hint.setStringValue_("Enter a number")
                self._threshold_hint.setHidden_(False)
                self._threshold_field.setTextColor_(NSColor.systemRedColor())
        else:
            self._threshold_hint.setHidden_(True)
            self._threshold_field.setTextColor_(NSColor.controlTextColor())

    def _save_and_close(self) -> None:
        cfg = self._config

        # Plan tier
        selected = self._tier_popup.titleOfSelectedItem()
        for key, display in PLAN_TIERS:
            if display == selected:
                cfg["plan_tier"] = key
                break

        # Auto refresh
        cfg["auto_refresh"] = bool(self._auto_refresh_switch.state())

        # Refresh interval (clamp to valid range)
        try:
            val = int(self._refresh_field.stringValue().strip())
            cfg["refresh_interval_sec"] = max(10, min(3600, val))
        except ValueError:
            pass

        # Notifications
        cfg["notifications_enabled"] = bool(self._notif_switch.state())

        # Warning threshold (clamp to valid range)
        try:
            val = int(self._threshold_field.stringValue().strip())
            cfg["warn_at_pct"] = max(1, min(100, val))
        except ValueError:
            pass

        save_config(cfg)
        self._on_save(cfg)
        SettingsWindow._instance = None
        logger.info("Settings saved")

    def _open_logs(self) -> None:
        if LOG_PATH.exists():
            NSWorkspace.sharedWorkspace().openFile_(str(LOG_PATH))
        else:
            self._update_status.setTextColor_(NSColor.secondaryLabelColor())
            self._update_status.setStringValue_("No log file found.")

    def _run_update(self) -> None:
        if self._updating:
            return
        self._updating = True
        self._update_btn.setEnabled_(False)
        self._update_btn.setTitle_("Updating...")
        self._update_status.setStringValue_("")

        delegate = self._delegate

        def _do():
            try:
                result = subprocess.run(
                    ["bash", str(_INSTALL_SCRIPT)],
                    cwd=str(_REPO_DIR),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                info = {"success": result.returncode == 0}
                if result.returncode != 0:
                    info["error"] = (result.stderr.strip().split("\n")[-1]
                                     if result.stderr else "Unknown error")
            except Exception as e:
                info = {"success": False, "error": str(e)}

            delegate.performSelectorOnMainThread_withObject_waitUntilDone_(
                "finishUpdate:", info, False
            )

        threading.Thread(target=_do, daemon=True).start()
