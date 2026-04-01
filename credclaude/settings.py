"""Native macOS settings window for CredClaude."""

from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path
from typing import Callable

import objc
from AppKit import (
    NSAttributedString,
    NSBackingStoreBuffered,
    NSButton,
    NSCenterTextAlignment,
    NSClosableWindowMask,
    NSColor,
    NSEvent,
    NSEventMaskKeyDown,
    NSEventModifierFlagCommand,
    NSFont,
    NSForegroundColorAttributeName,
    NSImage,
    NSLeftTextAlignment,
    NSMakeRect,
    NSMiniaturizableWindowMask,
    NSObject,
    NSPopUpButton,
    NSRightTextAlignment,
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

_W = 500
_H = 510
_PAD = 24
_INNER = 18
_ROW_H = 44


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


def _section_label(text: str, x: float, y: float) -> NSTextField:
    lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, _W - 2 * _PAD, 16))
    lbl.setStringValue_(text.upper())
    lbl.setBezeled_(False)
    lbl.setDrawsBackground_(False)
    lbl.setEditable_(False)
    lbl.setSelectable_(False)
    lbl.setAlignment_(NSLeftTextAlignment)
    lbl.setFont_(NSFont.systemFontOfSize_(11))
    lbl.setTextColor_(NSColor.secondaryLabelColor())
    return lbl


def _separator(parent: NSView, y: float) -> NSView:
    box_w = _W - 2 * _PAD
    sep = NSView.alloc().initWithFrame_(NSMakeRect(0, y, box_w, 1))
    sep.setWantsLayer_(True)
    sep.layer().setBackgroundColor_(NSColor.separatorColor().CGColor())
    parent.addSubview_(sep)
    return sep


def _chevron(parent: NSView, row_y: float, color: object = None) -> NSTextField:
    box_w = _W - 2 * _PAD
    lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(box_w - _INNER - 14, row_y + 12, 14, 20))
    lbl.setStringValue_("›")
    lbl.setBezeled_(False)
    lbl.setDrawsBackground_(False)
    lbl.setEditable_(False)
    lbl.setSelectable_(False)
    lbl.setAlignment_(NSRightTextAlignment)
    lbl.setFont_(NSFont.systemFontOfSize_(16))
    lbl.setTextColor_(color if color else NSColor.secondaryLabelColor())
    parent.addSubview_(lbl)
    return lbl


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
            sw._refresh_field.setEditable_(enabled)
            sw._refresh_field.setEnabled_(enabled)
            sw._unit_popup.setEnabled_(enabled)

    def onAutoReauthToggle_(self, sender):
        # Toggle is persisted on window close; no immediate side effects needed.
        _ = sender

    def onResetDefaults_(self, sender):
        sw = self.settings_window
        if sw:
            sw._reset_to_defaults()

    def onUnitChange_(self, sender):
        sw = self.settings_window
        if sw is None:
            return
        new_unit = str(sender.titleOfSelectedItem())
        if new_unit == sw._current_unit:
            return
        try:
            raw = int(sw._refresh_field.stringValue().strip())
        except ValueError:
            raw = 0
        if sw._current_unit == "sec" and new_unit == "min":
            converted = int(round(raw / 60))
        elif sw._current_unit == "min" and new_unit == "sec":
            converted = raw * 60
        else:
            converted = raw
        sw._current_unit = new_unit
        sw._refresh_field.setStringValue_(str(converted))

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

    def __init__(self, config: dict, on_save: Callable[[dict], None],
                 data_source: str = "OAuth (Live)") -> None:
        self._config = config.copy()
        self._on_save = on_save
        self._data_source = data_source
        self._updating = False
        self._event_monitor = None

    @classmethod
    def show(cls, config: dict, on_save: Callable[[dict], None],
             data_source: str = "OAuth (Live)") -> None:
        if cls._instance is not None:
            cls._instance._window.makeKeyAndOrderFront_(None)
            return
        inst = cls(config, on_save, data_source)
        cls._instance = inst
        inst._build()
        inst._window.makeFirstResponder_(inst._window.contentView())  # prevent blue focus ring
        inst._window.center()
        inst._window.makeKeyAndOrderFront_(None)

    def _build(self) -> None:
        style = NSTitledWindowMask | NSClosableWindowMask | NSMiniaturizableWindowMask
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, _W, _H), style, NSBackingStoreBuffered, False
        )
        self._window.setTitle_("CredClaude Settings")
        self._window.setReleasedWhenClosed_(False)

        if _ICON_PATH.exists():
            ns_icon = NSImage.alloc().initWithContentsOfFile_(str(_ICON_PATH))
            if ns_icon:
                self._window.setMiniwindowImage_(ns_icon)

        self._delegate = _Delegate.alloc().init()
        self._delegate.settings_window = self
        self._window.setDelegate_(self._delegate)

        self._field_delegate = _FieldDelegate.alloc().init()
        self._field_delegate.settings_window = self

        content = self._window.contentView()
        box_w = _W - 2 * _PAD   # 452
        self._current_unit = "sec"

        # Hidden update status label (used programmatically by finishUpdate_)
        self._update_status = _label(
            "", 0, 4, w=_W, h=14, size=10,
            color=NSColor.secondaryLabelColor()
        )
        self._update_status.setAlignment_(NSCenterTextAlignment)
        content.addSubview_(self._update_status)

        # =================================================================
        # Footer
        # =================================================================
        footer = _label(
            "Settings are saved automatically",
            0, 20, w=_W, h=16, size=11,
            color=NSColor.tertiaryLabelColor()
        )
        footer.setAlignment_(NSCenterTextAlignment)
        content.addSubview_(footer)

        # =================================================================
        # Reset to Defaults — standalone at very bottom
        # =================================================================
        reset_box = _section_box(66, 44)
        content.addSubview_(reset_box)

        reset_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(_INNER, 0, box_w - 2 * _INNER - 24, _ROW_H)
        )
        red_title = NSAttributedString.alloc().initWithString_attributes_(
            "Reset to Defaults",
            {NSForegroundColorAttributeName: NSColor.systemRedColor()}
        )
        reset_btn.setAttributedTitle_(red_title)
        reset_btn.setBordered_(False)
        reset_btn.setAlignment_(NSLeftTextAlignment)
        reset_btn.setFont_(NSFont.systemFontOfSize_(13))
        reset_btn.setTarget_(self._delegate)
        reset_btn.setAction_(
            objc.selector(self._delegate.onResetDefaults_, signature=b"v@:@")
        )
        reset_box.addSubview_(reset_btn)
        _chevron(reset_box, 0, color=NSColor.systemRedColor())

        # =================================================================
        # ACTIONS section  (label y=222, box y=126 h=88)
        # =================================================================
        content.addSubview_(_section_label("Actions", _PAD, 222))
        box = _section_box(126, 88)
        content.addSubview_(box)

        # Row 1 — bottom: Check for Updates (local y=0..44)
        self._update_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(_INNER, 0, box_w - 2 * _INNER - 24, _ROW_H)
        )
        self._update_btn.setTitle_("Check for Updates")
        self._update_btn.setBordered_(False)
        self._update_btn.setAlignment_(NSLeftTextAlignment)
        self._update_btn.setFont_(NSFont.systemFontOfSize_(13))
        self._update_btn.setTarget_(self._delegate)
        self._update_btn.setAction_(
            objc.selector(self._delegate.onUpdate_, signature=b"v@:@")
        )
        box.addSubview_(self._update_btn)
        _chevron(box, 0)

        _separator(box, 44)

        # Row 2 — top: View Logs (local y=44..88)
        self._logs_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(_INNER, 44, box_w - 2 * _INNER - 24, _ROW_H)
        )
        self._logs_btn.setTitle_("View Logs")
        self._logs_btn.setBordered_(False)
        self._logs_btn.setAlignment_(NSLeftTextAlignment)
        self._logs_btn.setFont_(NSFont.systemFontOfSize_(13))
        self._logs_btn.setTarget_(self._delegate)
        self._logs_btn.setAction_(
            objc.selector(self._delegate.onViewLogs_, signature=b"v@:@")
        )
        box.addSubview_(self._logs_btn)
        _chevron(box, 44)

        # =================================================================
        # SYSTEM section  (label y=350, box y=254 h=88)
        # =================================================================
        content.addSubview_(_section_label("System", _PAD, 350))
        box = _section_box(254, 88)
        content.addSubview_(box)

        # Row 2 — top: Version (local y=44..88)
        box.addSubview_(_label("Version", _INNER, 56))
        ver_lbl = _label(
            str(__version__),
            box_w - _INNER - 100, 56, w=100, h=20,
            color=NSColor.secondaryLabelColor()
        )
        ver_lbl.setAlignment_(NSRightTextAlignment)
        box.addSubview_(ver_lbl)

        _separator(box, 44)

        # Row 1 — bottom: Data source (local y=0..44)
        box.addSubview_(_label("Data source", _INNER, 12))

        # Dot indicator color depends on source state
        _ds_lower = self._data_source.lower()
        if "unavailable" in _ds_lower or "estimated" in _ds_lower:
            _dot_color = NSColor.systemOrangeColor()
        else:
            _dot_color = NSColor.systemGreenColor()

        dot = NSView.alloc().initWithFrame_(NSMakeRect(box_w - _INNER - 110, 18, 8, 8))
        dot.setWantsLayer_(True)
        dot.layer().setBackgroundColor_(_dot_color.CGColor())
        dot.layer().setCornerRadius_(4)
        box.addSubview_(dot)

        src_lbl = _label(
            self._data_source,
            box_w - _INNER - 100, 12, w=100, h=20,
            color=_dot_color
        )
        src_lbl.setAlignment_(NSRightTextAlignment)
        box.addSubview_(src_lbl)

        # =================================================================
        # MONITORING section  (label y=478, box y=378 h=132)
        # =================================================================
        content.addSubview_(_section_label("Monitoring", _PAD, 478))
        box = _section_box(378, 132)
        content.addSubview_(box)

        auto_refresh_on = self._config.get("auto_refresh", True)
        auto_reauth_on = self._config.get("auto_reauth_enabled", True)

        # Row 3 — top: Auto re-authenticate toggle (local y=88..132)
        box.addSubview_(_label("Auto re-authenticate", _INNER, 100))
        self._auto_reauth_switch = NSSwitch.alloc().initWithFrame_(
            NSMakeRect(box_w - _INNER - 40, 99, 40, 22)
        )
        self._auto_reauth_switch.setState_(1 if auto_reauth_on else 0)
        self._auto_reauth_switch.setTarget_(self._delegate)
        self._auto_reauth_switch.setAction_(
            objc.selector(self._delegate.onAutoReauthToggle_, signature=b"v@:@")
        )
        box.addSubview_(self._auto_reauth_switch)

        _separator(box, 88)

        # Row 2 — middle: Auto-refresh toggle (local y=44..88)
        box.addSubview_(_label("Auto-refresh", _INNER, 56))
        self._auto_refresh_switch = NSSwitch.alloc().initWithFrame_(
            NSMakeRect(box_w - _INNER - 40, 55, 40, 22)
        )
        self._auto_refresh_switch.setState_(1 if auto_refresh_on else 0)
        self._auto_refresh_switch.setTarget_(self._delegate)
        self._auto_refresh_switch.setAction_(
            objc.selector(self._delegate.onAutoRefreshToggle_, signature=b"v@:@")
        )
        box.addSubview_(self._auto_refresh_switch)

        _separator(box, 44)

        # Row 1 — bottom: Refresh interval + unit (local y=0..44)
        box.addSubview_(_label("Refresh interval", _INNER, 12))

        self._unit_popup = NSPopUpButton.alloc().initWithFrame_(
            NSMakeRect(box_w - _INNER - 60, 11, 60, 22)
        )
        self._unit_popup.addItemWithTitle_("sec")
        self._unit_popup.addItemWithTitle_("min")
        self._unit_popup.setTarget_(self._delegate)
        self._unit_popup.setAction_(
            objc.selector(self._delegate.onUnitChange_, signature=b"v@:@")
        )
        self._unit_popup.setFocusRingType_(1)  # NSFocusRingTypeNone
        self._unit_popup.setEnabled_(auto_refresh_on)
        box.addSubview_(self._unit_popup)

        self._refresh_field = _input_field(box_w - _INNER - 135, 11, 70, 22)
        self._refresh_field.setStringValue_(
            str(self._config.get("refresh_interval_sec", REFRESH_INTERVAL_SEC))
        )
        self._refresh_field.setEditable_(auto_refresh_on)
        self._refresh_field.setEnabled_(auto_refresh_on)
        self._refresh_field.setFocusRingType_(1)  # NSFocusRingTypeNone
        self._refresh_field.setDelegate_(self._field_delegate)
        box.addSubview_(self._refresh_field)

        # Install Cmd+W handler so the window closes like any normal macOS window
        def _cmd_w_handler(event):
            if (event.modifierFlags() & NSEventModifierFlagCommand and
                    event.charactersIgnoringModifiers() == "w"):
                self._window.performClose_(None)
                return None
            return event

        self._event_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown, _cmd_w_handler
        )

    def _reset_to_defaults(self) -> None:
        self._auto_reauth_switch.setState_(1)
        self._auto_refresh_switch.setState_(1)
        self._current_unit = "sec"
        self._unit_popup.selectItemWithTitle_("sec")
        self._refresh_field.setStringValue_(str(REFRESH_INTERVAL_SEC))
        self._refresh_field.setEditable_(True)
        self._refresh_field.setEnabled_(True)
        self._unit_popup.setEnabled_(True)

    def _save_and_close(self) -> None:
        if self._event_monitor is not None:
            NSEvent.removeMonitor_(self._event_monitor)
            self._event_monitor = None

        cfg = self._config

        # Auto refresh
        cfg["auto_refresh"] = bool(self._auto_refresh_switch.state())
        cfg["auto_reauth_enabled"] = bool(self._auto_reauth_switch.state())

        # Refresh interval (clamp to valid range, convert units)
        try:
            raw = int(self._refresh_field.stringValue().strip())
            if self._current_unit == "min":
                raw = raw * 60
            cfg["refresh_interval_sec"] = max(10, min(3600, raw))
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
