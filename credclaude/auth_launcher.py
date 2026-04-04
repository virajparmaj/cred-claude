"""Helpers for launching Claude re-authentication from CredClaude."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import subprocess
import time

logger = logging.getLogger(__name__)


AUTH_ERROR_MARKERS = (
    "claude auth login",
    "token expired",
    "oauth token has expired",
    "unauthorized",
)


def is_auth_error(error: str | None) -> bool:
    """Return True when the provider error indicates re-auth is required."""
    if not error:
        return False
    text = error.lower()
    if any(marker in text for marker in AUTH_ERROR_MARKERS):
        return True
    return "token" in text and "auth" in text


@dataclass(frozen=True)
class LaunchResult:
    """Result of attempting to launch `claude auth login`."""

    success: bool
    message: str


class ReauthGate:
    """In-memory cooldown gate used to avoid repeated auth popups."""

    def __init__(self, cooldown_sec: int = 1800) -> None:
        self._cooldown_sec = max(30, int(cooldown_sec))
        self._last_attempt_mono = 0.0

    def update_cooldown(self, cooldown_sec: int) -> None:
        self._cooldown_sec = max(30, int(cooldown_sec))

    def mark_attempt(self, now_mono: float | None = None) -> None:
        self._last_attempt_mono = now_mono if now_mono is not None else time.monotonic()

    def seconds_until_next_attempt(self, now_mono: float | None = None) -> int:
        now = now_mono if now_mono is not None else time.monotonic()
        if self._last_attempt_mono <= 0:
            return 0
        elapsed = now - self._last_attempt_mono
        if elapsed >= self._cooldown_sec:
            return 0
        return int(self._cooldown_sec - elapsed)

    def eligible_for_auto_launch(self, error: str | None, now_mono: float | None = None) -> bool:
        if not is_auth_error(error):
            return False
        return self.seconds_until_next_attempt(now_mono=now_mono) == 0


def _build_terminal_auth_script() -> str:
    """Build AppleScript used to launch `claude auth login` safely.

    Behavior:
    - Terminal already running: create a dedicated window and run login there.
    - Terminal not running: open one window and run login in it.
    """
    return (
        'set launch_mode to "single_window_cold_start"\n'
        'if application "Terminal" is running then\n'
        '  set launch_mode to "dedicated_window_existing_terminal"\n'
        '  do shell script "open -na Terminal"\n'
        '  tell application "Terminal"\n'
        "    repeat 20 times\n"
        "      if (count of windows) > 0 then exit repeat\n"
        "      delay 0.1\n"
        "    end repeat\n"
        "    if (count of windows) > 0 then\n"
        '      do script "claude auth login" in selected tab of front window\n'
        "    else\n"
        '      do script "claude auth login"\n'
        "    end if\n"
        "    activate\n"
        "  end tell\n"
        "else\n"
        '  tell application "Terminal"\n'
        '    do script "claude auth login"\n'
        "    activate\n"
        "  end tell\n"
        "end if\n"
        "return launch_mode\n"
    )


def _extract_launch_mode(stdout: str | None) -> str | None:
    """Extract launch mode marker returned by AppleScript."""
    if not stdout:
        return None
    mode = stdout.strip().splitlines()[-1].strip().strip('"')
    return mode or None


def launch_claude_auth_login(timeout_sec: int = 12) -> LaunchResult:
    """Open Terminal and run `claude auth login`.

    Browser authorization still requires user action.
    """
    script = _build_terminal_auth_script()
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        return LaunchResult(False, "Timed out while asking macOS to open Terminal.")
    except FileNotFoundError:
        return LaunchResult(False, "osascript is unavailable on this machine.")
    except Exception as exc:
        return LaunchResult(False, f"Failed to launch Terminal: {exc}")

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if "not allowed" in detail.lower():
            return LaunchResult(
                False,
                "macOS denied Terminal automation. Allow permissions in System Settings.",
            )
        if detail:
            return LaunchResult(False, f"Terminal launch failed: {detail}")
        return LaunchResult(False, f"Terminal launch failed (exit {result.returncode}).")

    launch_mode = _extract_launch_mode(result.stdout)
    if launch_mode in {"dedicated_window_existing_terminal", "single_window_cold_start"}:
        logger.info("Re-auth Terminal launch mode: %s", launch_mode)
    elif launch_mode:
        logger.info("Re-auth Terminal launch mode (unknown): %s", launch_mode)

    return LaunchResult(
        True,
        "Opened Terminal and started `claude auth login`. Complete browser approval to finish.",
    )
