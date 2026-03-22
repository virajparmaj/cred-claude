"""Native macOS preferences window for CredClaude."""

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
    NSClosableWindowMask,
    NSColor,
    NSFont,
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
)

from credclaude import __version__
from credclaude.config import load_config, save_config, REFRESH_INTERVAL_SEC

logger = logging.getLogger("credclaude.preferences")

_REPO_DIR = Path(__file__).parent.parent
_INSTALL_SCRIPT = _REPO_DIR / "install.sh"

PLAN_TIERS = [
    ("pro", "Pro ($20/mo)"),
    ("max_5x", "Max 5x ($100/mo)"),
    ("max_20x", "Max 20x ($200/mo)"),
]

_W = 420
_H = 430
_PAD = 20
_FIELD_W = 100


def _label(text: str, x: float, y: float, w: float = 200, h: float = 20,
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
    box.layer().setCornerRadius_(8)
    return box


class _Delegate(NSObject):
    """Window delegate + button action handler."""

    pref_window = objc.ivar()

    def windowWillClose_(self, notification):
        pw = self.pref_window
        if pw:
            pw._save_and_close()

    def onUpdate_(self, sender):
        pw = self.pref_window
        if pw:
            pw._run_update()

    def finishUpdate_(self, info):
        pw = self.pref_window
        if pw:
            success = info["success"]
            error = info.get("error", "")
            pw._updating = False
            pw._update_btn.setEnabled_(True)
            pw._update_btn.setTitle_("Check for Updates")
            if success:
                pw._update_status.setTextColor_(NSColor.systemGreenColor())
                pw._update_status.setStringValue_("CredClaude is up to date.")
            else:
                pw._update_status.setTextColor_(NSColor.systemRedColor())
                pw._update_status.setStringValue_(f"Update failed: {error[:50]}")


class PreferencesWindow:
    """Singleton native preferences window."""

    _instance: PreferencesWindow | None = None

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
        self._window.setTitle_("CredClaude Preferences")
        self._window.setReleasedWhenClosed_(False)

        self._delegate = _Delegate.alloc().init()
        self._delegate.pref_window = self
        self._window.setDelegate_(self._delegate)

        content = self._window.contentView()
        y = _H - 50
        box_w = _W - 2 * _PAD

        # === General ===
        content.addSubview_(_label("General", _PAD, y, bold=True, size=14))
        y -= 8
        box = _section_box(y - 65, 65)
        content.addSubview_(box)

        # Refresh Interval
        ry = 35
        box.addSubview_(_label("Refresh Interval", 15, ry))
        self._refresh_field = _input_field(box_w - 110, ry, 55)
        self._refresh_field.setStringValue_(str(self._config.get("refresh_interval_sec", REFRESH_INTERVAL_SEC)))
        box.addSubview_(self._refresh_field)
        box.addSubview_(_label("seconds", box_w - 52, ry + 2, w=50, size=11,
                               color=NSColor.secondaryLabelColor()))

        # Plan Tier
        ry = 5
        box.addSubview_(_label("Plan Tier", 15, ry))
        self._tier_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(box_w - 165, ry - 2, 150, 25), False
        )
        current_tier = self._config.get("plan_tier", "pro")
        for key, display in PLAN_TIERS:
            self._tier_popup.addItemWithTitle_(display)
            if key == current_tier:
                self._tier_popup.selectItemWithTitle_(display)
        box.addSubview_(self._tier_popup)

        y -= 85

        # === Notifications ===
        content.addSubview_(_label("Notifications", _PAD, y, bold=True, size=14))
        y -= 8
        box = _section_box(y - 65, 65)
        content.addSubview_(box)

        ry = 35
        box.addSubview_(_label("Notifications", 15, ry))
        self._notif_switch = NSSwitch.alloc().initWithFrame_(NSMakeRect(box_w - 55, ry, 40, 22))
        self._notif_switch.setState_(1 if self._config.get("notifications_enabled", True) else 0)
        box.addSubview_(self._notif_switch)

        ry = 5
        box.addSubview_(_label("Warning Threshold", 15, ry))
        self._threshold_field = _input_field(box_w - 80, ry, 40)
        self._threshold_field.setStringValue_(str(self._config.get("warn_at_pct", 80)))
        box.addSubview_(self._threshold_field)
        box.addSubview_(_label("%", box_w - 35, ry + 2, w=20, size=11,
                               color=NSColor.secondaryLabelColor()))

        y -= 85

        # === Updates ===
        content.addSubview_(_label("Updates", _PAD, y, bold=True, size=14))
        y -= 8
        box = _section_box(y - 50, 50)
        content.addSubview_(box)

        ry = 15
        self._version_label = _label(f"Version {__version__}", 15, ry)
        box.addSubview_(self._version_label)

        self._update_status = _label("", 15, ry - 16, w=200, h=15, size=11,
                                      color=NSColor.secondaryLabelColor())
        box.addSubview_(self._update_status)

        self._update_btn = NSButton.alloc().initWithFrame_(NSMakeRect(box_w - 155, ry - 3, 140, 25))
        self._update_btn.setTitle_("Check for Updates")
        self._update_btn.setBezelStyle_(NSBezelStyleRounded)
        self._update_btn.setTarget_(self._delegate)
        self._update_btn.setAction_(objc.selector(self._delegate.onUpdate_, signature=b"v@:@"))
        box.addSubview_(self._update_btn)

    def _save_and_close(self) -> None:
        cfg = self._config

        try:
            val = int(self._refresh_field.stringValue().strip())
            cfg["refresh_interval_sec"] = max(10, val)
        except ValueError:
            pass

        selected = self._tier_popup.titleOfSelectedItem()
        for key, display in PLAN_TIERS:
            if display == selected:
                cfg["plan_tier"] = key
                break

        cfg["notifications_enabled"] = bool(self._notif_switch.state())

        try:
            val = int(self._threshold_field.stringValue().strip())
            if 1 <= val <= 100:
                cfg["warn_at_pct"] = val
        except ValueError:
            pass

        save_config(cfg)
        self._on_save(cfg)
        PreferencesWindow._instance = None
        logger.info("Preferences saved")

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
