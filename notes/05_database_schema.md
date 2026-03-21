# 05 Database Schema

## Status: Not Applicable

No database exists. All persistence uses local files and in-memory state.

### Why this is intentionally empty

- [Confirmed from code] No SQLite, PostgreSQL, Supabase, or any database driver is imported or referenced.
- [Confirmed from code] The only external dependency is `rumps>=0.4.0` (`requirements.txt:1`).

### Actual persistence model

| Store | Path | Format | Purpose |
|---|---|---|---|
| Config | `~/.credclaude/config.json` | JSON | User settings: `billing_day`, `daily_budget_usd`, `warn_at_pct`, `notifications_enabled` (`monitor.py:55-60`, `monitor.py:105-108`) |
| Reset notification lock | `~/.credclaude/.last_reset_notif` | Plain text (ISO date) | Prevents duplicate billing-reset notifications per day (`monitor.py:363-371`, `monitor.py:548-553`) |
| Budget warning locks | `~/.credclaude/.warn_{YYYY-MM-DD}` | Plain text (ISO date) | One file per day, prevents duplicate budget warnings (`monitor.py:560-566`) |
| Stdout log | `~/.credclaude/monitor.log` | Plain text | Captured by launchd (`install.sh:54-55`) |
| Stderr log | `~/.credclaude/monitor.err` | Plain text | Captured by launchd (`install.sh:57-58`) |
| File cache | In-memory `self._file_cache` dict | `{filepath: (file_size, CostData)}` | Avoids re-parsing unchanged JSONL files within the same day (`monitor.py:193-209`, `monitor.py:459-463`) |

### Data source (read-only)

- Claude session logs at `~/.claude/projects/*/*.jsonl` and `~/.claude/projects/*/*/subagents/*.jsonl` (`monitor.py:161-170`).
- These files are written by Claude Code, not by this app. The monitor only reads them.

### When this would change

A database would only become relevant if the project adds historical trend storage, export, or multi-device sync. None of these are currently implemented.
