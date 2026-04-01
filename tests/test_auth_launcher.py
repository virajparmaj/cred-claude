"""Tests for re-auth launcher helpers."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from credclaude.auth_launcher import (
    ReauthGate,
    is_auth_error,
    launch_claude_auth_login,
)


class TestLaunchClaudeAuthLogin:
    def test_success(self):
        mock = MagicMock(returncode=0, stderr="", stdout="")
        with patch("subprocess.run", return_value=mock) as run_mock:
            result = launch_claude_auth_login()

        assert result.success is True
        assert "Opened Terminal" in result.message
        args, kwargs = run_mock.call_args
        assert args[0][:2] == ["osascript", "-e"]
        assert "claude auth login" in args[0][2]
        assert kwargs["timeout"] == 12

    def test_permission_denied(self):
        mock = MagicMock(returncode=1, stderr="Not allowed to send keystrokes", stdout="")
        with patch("subprocess.run", return_value=mock):
            result = launch_claude_auth_login()

        assert result.success is False
        assert "denied" in result.message.lower()

    def test_timeout_failure(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="osascript", timeout=12)):
            result = launch_claude_auth_login()

        assert result.success is False
        assert "Timed out" in result.message


class TestReauthGate:
    def test_auth_failure_triggers_once_per_cooldown(self):
        gate = ReauthGate(cooldown_sec=1800)
        err = "Token expired — run: claude auth login"

        assert gate.eligible_for_auto_launch(err, now_mono=100.0) is True
        gate.mark_attempt(now_mono=100.0)
        assert gate.eligible_for_auto_launch(err, now_mono=200.0) is False
        assert gate.eligible_for_auto_launch(err, now_mono=1901.0) is True

    def test_non_auth_error_never_triggers(self):
        gate = ReauthGate(cooldown_sec=1800)
        assert gate.eligible_for_auto_launch("Rate limited", now_mono=100.0) is False
        assert gate.eligible_for_auto_launch(None, now_mono=100.0) is False

    def test_is_auth_error_markers(self):
        assert is_auth_error("Token expired — run: claude auth login") is True
        assert is_auth_error("OAuth token has expired.") is True
        assert is_auth_error("Rate limited") is False
