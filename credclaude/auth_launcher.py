"""Helpers for launching Claude re-authentication from CredClaude."""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
import time


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


def launch_claude_auth_login(timeout_sec: int = 12) -> LaunchResult:
    """Open Terminal and run `claude auth login`.

    Browser authorization still requires user action.
    """
    script = (
        'tell application "Terminal"\n'
        "  activate\n"
        '  do script "claude auth login"\n'
        "end tell\n"
    )
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

    return LaunchResult(
        True,
        "Opened Terminal and started `claude auth login`. Complete browser approval to finish.",
    )
