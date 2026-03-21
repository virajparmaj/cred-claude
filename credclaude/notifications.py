"""macOS notification delivery and lock-file management."""

from __future__ import annotations

import datetime
import logging
import subprocess
from pathlib import Path

from credclaude.config import APP_DIR

logger = logging.getLogger("credclaude.notifications")


def send_notification(title: str, message: str) -> None:
    """Send a macOS notification via osascript."""
    # Escape double-quotes for AppleScript
    safe_title = title.replace('"', '\\"')
    safe_msg = message.replace('"', '\\"')
    try:
        subprocess.run(
            [
                "osascript", "-e",
                f'display notification "{safe_msg}" with title "{safe_title}" sound name "Glass"',
            ],
            capture_output=True,
            timeout=10,
        )
        logger.debug("Notification sent: %s", title)
    except Exception as e:
        logger.warning("Failed to send notification: %s", e)


def read_lock(path: Path) -> str:
    """Read a lock file's content (ISO date string) or return empty."""
    if path.exists():
        return path.read_text().strip()
    return ""


def write_lock(path: Path) -> None:
    """Write today's ISO date to a lock file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(datetime.date.today().isoformat())


def cleanup_old_warn_locks(app_dir: Path | None = None, days: int = 7) -> None:
    """Delete .warn_* lock files older than `days` days."""
    target = app_dir or APP_DIR
    if not target.exists():
        return
    cutoff = datetime.date.today() - datetime.timedelta(days=days)
    for f in target.glob(".warn_*"):
        try:
            # Filename: .warn_YYYY-MM-DD
            date_str = f.name.removeprefix(".warn_")
            file_date = datetime.date.fromisoformat(date_str)
            if file_date < cutoff:
                f.unlink()
                logger.debug("Cleaned up old warn lock: %s", f.name)
        except (ValueError, OSError) as e:
            logger.debug("Skipping warn lock cleanup for %s: %s", f.name, e)
