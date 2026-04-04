# 07 User Flows

## Purpose
Describe real end-user flows and where they are complete or incomplete.

## Status
- [Confirmed from code] All main flows implemented: install, first-run, monitoring, settings, notifications, re-auth.

## Confirmed from code

- **Install flow**:
  1. Run `bash install.sh`.
  2. venv created, `credclaude` package installed via `pip install -e .`.
  3. `.app` bundle built via `build_app.sh`, copied to `~/Applications/CredClaude.app`.
  4. launchd plist written; `open -a CredClaude` fires immediately.
  (`install.sh`)

- **First-run onboarding flow**:
  1. No config found → prompts for billing reset day, daily budget, plan tier.
  2. Saves config to `~/.credclaude/config.json`.
  3. Copies `default_pricing.json` to `~/.credclaude/pricing.json`.
  (`credclaude/app.py`, `credclaude/config.py`)

- **Daily monitoring flow**:
  1. 5s after start: fetch OAuth utilization + scan JSONL files.
  2. Every 60s: refresh menu — session %, weekly %, extra usage, reset countdowns, daily spend, period total, model breakdown.
  3. Weekly and extra-usage sections hidden when API returns no data for those fields.
  (`credclaude/app.py`, `credclaude/limit_providers.py`, `credclaude/ingestion.py`)

- **Settings update flow**:
  1. Open Settings menu item → sequential modal dialogs.
  2. Update billing day, budget, warn threshold, notifications toggle, plan tier.
  3. Persist config and force immediate refresh.
  (`credclaude/app.py`)

- **Notification flow**:
  1. Checked every refresh cycle.
  2. Budget threshold: send notification once per day via lock file.
  3. Billing reset: send notification once per reset day.
  (`credclaude/notifications.py`)

- **Token expiry / re-auth flow (automatic)**:
  1. OAuth returns 401 → app first attempts silent token refresh.
  2. If silent refresh succeeds, usage fetch retried immediately.
  3. If silent refresh fails → 5-min cooldown; menu shows "(stale)" + error.
  4. On each update cycle, `_maybe_auto_reauth()` checks if error is auth-related and `ReauthGate` cooldown (default 30 min) has elapsed.
  5. If eligible: opens Terminal via AppleScript and runs `claude auth login` automatically.
  6. User completes browser authorization; clicks "Refresh Now" to resume live data.
  7. Manual "Re-authenticate" menu item triggers this immediately regardless of cooldown.
  (`credclaude/limit_providers.py`, `credclaude/auth_launcher.py`, `credclaude/app.py`)

- **Rate limit flow**:
  1. OAuth returns 429 → exponential backoff (120s → 300s → 600s).
  2. Last known data displayed during backoff; countdown shown in menu.
  3. "Refresh Now" during backoff clears local state but may escalate backoff tier if server window hasn't reset.
  (`credclaude/limit_providers.py`)

## Inferred / proposed
- [Not found in repository] No signup/login flow (not required for current local architecture).
- [Not found in repository] No dashboard/profile/admin flow.

## Important details
- "Landing" is the menu bar title state after launch, not a webpage.
- Core interaction is passive monitoring; user interaction is mostly settings and occasional refresh.

## Open issues / gaps
- No explicit flow for missing log directory (`~/.claude/projects`) or permission problems.
- No guided recovery for corrupted config file (falls back to defaults silently).
- No "Open logs" menu action for easier support/troubleshooting.

## Recommended next steps
- Add user-visible status line for "data source found / not found".
- Add "Open logs folder" menu action.
