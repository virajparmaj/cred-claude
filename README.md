# CredClaude

<div align="center">
    <img src="claude_monitor_logo.png" alt="CredClaude logo" width="200"/>
</div>

## What is CredClaude?

**A macOS menu bar app that tracks your Claude Code API usage costs in real-time.**

CredClaude monitors your Claude Code sessions locally and displays your daily compute costs directly in your macOS menu bar. It scans your session files, calculates token-based USD costs, and shows daily budgets, model breakdowns, and billing period totals — all without leaving your local machine.

### Key Features

- **Daily cost tracking** — See today's spend vs. your daily budget in the menu bar
- **Per-model breakdown** — View costs by Claude model (Opus, Sonnet, Haiku)
- **Billing period totals** — Track cumulative spending and countdown to billing reset
- **Configurable alerts** — Get notified when you hit 80% of your daily budget
- **Auto-start on login** — Runs silently in the background after installation
- **Zero data leakage** — All analysis stays local; no data sent to external servers

## How It Looks When Operating

Once installed, CredClaude appears in your macOS menu bar (top-right). The display shows your current session usage and reset countdown:

```
65% | 8h 14m
```

Click the menu bar icon to expand:

```
Refresh
Settings
————————
Quit
```

The display refreshes automatically every 60 seconds (configurable in Settings) and also triggers when you open the menu.

---

**Best-effort local macOS menu bar app for tracking Claude Code usage costs.**

This app reads your local Claude Code session files, computes token-based USD costs, and shows daily/billing-period totals in your menu bar. It estimates account limits based on your plan tier — all data stays local.

## What It Shows

- Daily cost vs estimated budget with progress bar
- Per-model breakdown (Opus / Sonnet / Haiku)
- 5-hour rolling window token usage
- Billing period total and reset countdown
- Data source and confidence labels (transparent about what's estimated)
- Pricing staleness warnings

## Important: This Is a Best-Effort Monitor

- **Limits are estimated**, not exact. Anthropic does not expose account limits via public API.
- **Plan tier budgets are community-derived approximations**, labeled with LOW confidence.
- **5-hour window** shows local token accumulation, not server-side remaining quota.
- **Weekly caps** exist but cannot be measured locally — shown as advisory note.
- **Pricing** is externalized and versioned, but requires manual updates when Anthropic changes rates.

## Installation

### Quick Start (Development Mode)

Run CredClaude directly from your terminal for testing:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m credclaude
```

The menu bar app will appear immediately. Press `Ctrl+C` to stop.

### Production Install (Recommended)

Install as a standalone macOS app bundle that auto-starts on login:

```bash
bash install.sh
```

**What the installer does:**
1. Creates a Python virtual environment
2. Installs dependencies
3. Builds a lightweight `.app` bundle
4. Installs to `~/Applications/CredClaude.app`
5. Registers a launchd agent for auto-start on every login
6. Starts the app immediately

**After installation:**
- The app runs in your menu bar automatically
- It auto-starts when you log in
- Config file lives at `~/.credclaude/config.json`
- Logs are saved to `~/.credclaude/monitor.log`

### Uninstall

To remove CredClaude completely:

```bash
bash uninstall.sh
```

This will:
1. Stop the running CredClaude process
2. Stop the launchd agent
3. Remove the `.app` from `~/Applications/`

Config and logs at `~/.credclaude/` are kept. Delete that folder manually for a full clean removal.

## Configuration

Config is stored at `~/.credclaude/config.json`:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `plan_tier` | string | `"pro"` | Your Claude Code plan: `pro`, `max_5x`, `max_20x` |
| `billing_day` | int | `1` | Day of month your billing resets (1-28) |
| `daily_budget_usd` | float\|null | `null` | Manual daily budget override. `null` = use plan estimate |
| `warn_at_pct` | int | `80` | Notification threshold (% of session usage) |
| `notifications_enabled` | bool | `true` | Enable/disable macOS notifications |
| `stale_threshold_minutes` | int | `30` | Minutes before data is considered stale |
| `auto_refresh` | bool | `true` | Enable automatic refresh on the set interval |
| `refresh_interval_sec` | int | `60` | Seconds between auto-refreshes (10–3600) |

All settings are also editable from the menu bar → Settings.

## Pricing

Model pricing is stored at `~/.credclaude/pricing.json` with an `updated_at` timestamp. The app warns you when pricing data is >30 days old.

To update pricing:
1. Check current rates at https://www.anthropic.com/pricing
2. Edit `~/.credclaude/pricing.json`
3. Update the `updated_at` field to today's date
4. Click "Refresh Now" in the menu bar

## Architecture

```
credclaude/
├── models.py           # Data classes (CostData, LimitInfo, etc.)
├── config.py           # Paths, defaults, config I/O, logging
├── cost_engine.py      # Pricing load, cost computation, timestamp parsing
├── ingestion.py        # JSONL scanning, file cache, 5h window estimation
├── billing.py          # Billing period math
├── formatting.py       # Progress bar, token/cost formatters
├── notifications.py    # macOS notifications, lock files
├── limit_providers.py  # Official OAuth API + Estimator fallback
└── app.py              # rumps menu bar UI
```

Data flow: `~/.claude/projects/**/*.jsonl` → parse → cost compute → aggregate → menu bar display

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Authentication

The app reads a Claude Code OAuth token from macOS Keychain to fetch live session usage. If the menu shows "Token expired":

```bash
claude auth login
```

Then click **Refresh Now** in the menu bar. See `notes/04_auth_and_roles.md` for details.

## Known Limitations

1. **OAuth API is the primary source** — falls back to plan-tier estimates when the token is expired or rate-limited. Stale data is shown from the last successful fetch.
2. **Plan tier limits are approximate** — labeled with LOW confidence.
3. **5-hour window is estimated** — based on local token accumulation, not server-side remaining quota.
4. **Weekly cap not tracked** — exists but cannot be measured locally.
5. **Pricing requires manual updates** — no machine-readable endpoint exists.
6. **macOS only** — depends on rumps, osascript, launchd.

## Requirements

- macOS (Apple Silicon or Intel)
- Python 3.11+
- Claude Code installed with session logs at `~/.claude/projects/`
