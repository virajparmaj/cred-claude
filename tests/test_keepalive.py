"""Tests for post-reset keepalive scheduling."""

from __future__ import annotations

import datetime
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from credclaude import keepalive as keepalive_mod
from credclaude.keepalive import KeepaliveScheduler


class _FrozenDateTime(datetime.datetime):
    current: datetime.datetime = datetime.datetime(2026, 4, 6, 12, 0, tzinfo=datetime.timezone.utc)

    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return cls.current.astimezone(tz)
        return cls.current


class _DummyTimer:
    def __init__(self, interval, function, args=None, kwargs=None):
        self.interval = interval
        self.function = function
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.daemon = False
        self.started = False
        self.cancelled = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True


@pytest.fixture
def frozen_now(monkeypatch):
    monkeypatch.setattr(keepalive_mod.datetime, "datetime", _FrozenDateTime)
    return _FrozenDateTime.current


@pytest.fixture
def timer_factory(monkeypatch):
    created: list[_DummyTimer] = []

    def _make_timer(interval, function, args=None, kwargs=None):
        timer = _DummyTimer(interval, function, args=args, kwargs=kwargs)
        created.append(timer)
        return timer

    monkeypatch.setattr(keepalive_mod.threading, "Timer", _make_timer)
    return created


class TestKeepaliveSchedulerSchedule:
    def test_future_resets_at_starts_timer(self, frozen_now, timer_factory):
        scheduler = KeepaliveScheduler()
        resets_at = frozen_now + datetime.timedelta(minutes=5)

        started = scheduler.schedule(resets_at)

        assert started is True
        assert len(timer_factory) == 1
        assert timer_factory[0].interval == pytest.approx(310.0)
        assert timer_factory[0].started is True
        assert timer_factory[0].daemon is True

    def test_past_resets_at_does_not_start_timer(self, frozen_now, timer_factory):
        scheduler = KeepaliveScheduler()
        resets_at = frozen_now - datetime.timedelta(seconds=1)

        started = scheduler.schedule(resets_at)

        assert started is False
        assert timer_factory == []

    def test_none_does_not_start_timer(self, timer_factory):
        scheduler = KeepaliveScheduler()

        started = scheduler.schedule(None)

        assert started is False
        assert timer_factory == []

    def test_reschedule_cancels_previous_timer(self, frozen_now, timer_factory):
        scheduler = KeepaliveScheduler()

        scheduler.schedule(frozen_now + datetime.timedelta(minutes=5))
        first_timer = timer_factory[0]

        scheduler.schedule(frozen_now + datetime.timedelta(minutes=10))

        assert len(timer_factory) == 2
        assert first_timer.cancelled is True
        assert timer_factory[1].started is True

    def test_cancel_cancels_pending_timer(self, frozen_now, timer_factory):
        scheduler = KeepaliveScheduler()
        scheduler.schedule(frozen_now + datetime.timedelta(minutes=5))

        scheduler.cancel()

        assert timer_factory[0].cancelled is True


class TestKeepaliveSchedulerFirePing:
    def test_success(self):
        scheduler = KeepaliveScheduler()
        mock_result = MagicMock(returncode=0, stderr="", stdout="pong")

        with patch("shutil.which", return_value="/usr/local/bin/claude"), patch(
            "subprocess.run", return_value=mock_result
        ) as run_mock:
            assert scheduler._fire_ping() is True

        args, kwargs = run_mock.call_args
        assert args[0] == ["/usr/local/bin/claude", "-p", "ping"]
        assert kwargs["timeout"] == 30

    def test_failure(self):
        scheduler = KeepaliveScheduler()
        mock_result = MagicMock(returncode=1, stderr="boom", stdout="")

        with patch("shutil.which", return_value="/usr/local/bin/claude"), patch(
            "subprocess.run", return_value=mock_result
        ):
            assert scheduler._fire_ping() is False

    def test_timeout(self):
        scheduler = KeepaliveScheduler()

        with patch("shutil.which", return_value="/usr/local/bin/claude"), patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=30),
        ):
            assert scheduler._fire_ping() is False

    def test_claude_not_found(self):
        scheduler = KeepaliveScheduler()

        with patch("shutil.which", return_value=None), patch("subprocess.run") as run_mock:
            assert scheduler._fire_ping() is False

        run_mock.assert_not_called()
