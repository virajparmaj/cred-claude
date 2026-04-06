"""Scheduler for sending a small Claude keepalive ping after session reset."""

from __future__ import annotations

import datetime
import logging
import shutil
import subprocess
import threading

logger = logging.getLogger("credclaude.keepalive")


class KeepaliveScheduler:
    """Schedule a post-reset ping so the next 5-hour window starts promptly."""

    def __init__(self, buffer_sec: int = 10, ping_timeout_sec: int = 30) -> None:
        self._buffer_sec = int(buffer_sec)
        self._ping_timeout_sec = int(ping_timeout_sec)
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._timer_generation = 0

    def schedule(self, resets_at: datetime.datetime | None) -> bool:
        """Schedule a keepalive ping shortly after `resets_at`."""
        if resets_at is None:
            return False

        reset_time = resets_at.astimezone()
        now = datetime.datetime.now().astimezone()
        if reset_time <= now:
            logger.debug("Skipping keepalive schedule for past reset time: %s", resets_at)
            return False
        fire_at = reset_time + datetime.timedelta(seconds=self._buffer_sec)
        delay_sec = (fire_at - now).total_seconds()

        with self._lock:
            old_timer = self._timer
            self._timer_generation += 1
            generation = self._timer_generation
            timer = threading.Timer(delay_sec, self._run_scheduled_ping, args=(generation,))
            timer.daemon = True
            self._timer = timer

        if old_timer is not None:
            old_timer.cancel()

        timer.start()
        logger.info("Scheduled keepalive ping in %.1fs for %s", delay_sec, fire_at.isoformat())
        return True

    def cancel(self) -> None:
        """Cancel any pending keepalive ping."""
        with self._lock:
            timer = self._timer
            self._timer = None
            self._timer_generation += 1
        if timer is not None:
            timer.cancel()

    def _run_scheduled_ping(self, generation: int) -> None:
        with self._lock:
            if generation != self._timer_generation:
                return
            self._timer = None
        self._fire_ping()

    def _fire_ping(self) -> bool:
        """Send a lightweight Claude prompt to start the next window promptly."""
        claude_path = shutil.which("claude")
        if not claude_path:
            logger.warning("Keepalive ping skipped: `claude` was not found in PATH.")
            return False

        try:
            result = subprocess.run(
                [claude_path, "-p", "ping"],
                capture_output=True,
                text=True,
                timeout=self._ping_timeout_sec,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Keepalive ping timed out after %ss.", self._ping_timeout_sec)
            return False
        except FileNotFoundError:
            logger.warning("Keepalive ping failed: `claude` became unavailable.")
            return False
        except Exception as exc:
            logger.warning("Keepalive ping failed: %s", exc)
            return False

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            if detail:
                logger.warning("Keepalive ping failed: %s", detail)
            else:
                logger.warning("Keepalive ping failed (exit %s).", result.returncode)
            return False

        logger.info("Keepalive ping sent successfully.")
        return True
