"""Entry point for CredClaude."""

import atexit
import fcntl
import os
import sys

from credclaude.config import APP_DIR, setup_logging

PID_PATH = APP_DIR / "monitor.pid"

_lock_fd = None


def _acquire_pid_lock() -> None:
    """Ensure only one instance of the monitor is running.

    Uses fcntl.flock() for atomic file locking, eliminating the TOCTOU
    race that existed with the previous PID-check approach.
    """
    global _lock_fd
    APP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _lock_fd = open(PID_PATH, "w")
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Another instance is already running. Exiting.", file=sys.stderr)
        sys.exit(0)
    _lock_fd.write(str(os.getpid()))
    _lock_fd.flush()
    atexit.register(_release_pid_lock)


def _release_pid_lock() -> None:
    """Release the PID lock file on exit."""
    global _lock_fd
    if _lock_fd:
        try:
            fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            _lock_fd.close()
        except OSError:
            pass
        PID_PATH.unlink(missing_ok=True)
        _lock_fd = None


def main() -> None:
    _acquire_pid_lock()
    setup_logging()
    # Import app after logging is configured so all modules pick up the logger.
    from credclaude.app import CredClaude  # noqa: E402

    CredClaude().run()


if __name__ == "__main__":
    main()
