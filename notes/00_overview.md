# 00 Overview

## Purpose
Document what this repository currently is, who it serves, and how close it is to the intended production level.

## Status
- [Confirmed from code] Functional local macOS menu bar utility at v1.0.0 (`credclaude/__init__.py`).
- [Confirmed from code] Fully refactored from single `monitor.py` into `credclaude/` Python package with tests, packaging, and a built `.app` bundle.

## Confirmed from code
- The app is a Python `rumps` menu bar app built as a proper package (`credclaude/`) with modules for ingestion, billing, cost computation, notifications, limit providers, auth launching, icon asset resolution, and time formatting.
- App does not appear in the Dock or CMD+Tab switcher — `NSApplicationActivationPolicyAccessory` is set at startup (`credclaude/app.py`).
- Primary data path: OAuth API (`https://api.anthropic.com/api/oauth/usage`) for live 5-hour session utilization, weekly utilization, and extra usage; JSONL file scanning for daily/billing-period USD cost.
- First-run setup prompts for billing reset day and daily budget (`credclaude/config.py`).
- macOS notifications for billing reset and budget threshold via `osascript` (`credclaude/notifications.py`).
- `install.sh` builds a `.app` bundle via `build_app.sh`, copies it to `~/Applications`, and registers a `launchd` login item that runs `open -a CredClaude`.
- Uninstall unloads/removes the launch agent plist and optionally removes the `.app` (`uninstall.sh`).

## Inferred / proposed
- [Strongly inferred] Primary user is an individual Claude Code power user wanting quick session and budget visibility without opening dashboards.
- [Strongly inferred] Quality bar: reliable always-on personal observability tool. v1.0.0 is the first fully packaged release.
- [Not found in repository] No web frontend, backend server, authentication layer, database, or cloud deployment stack.

## Important details
- Core journey: install → `.app` auto-starts via launchd → first-run prompts → passive monitoring in menu bar → OAuth data for session limits + JSONL data for spend → optional settings updates.
- Cost model uses an externalized `~/.credclaude/pricing.json` (shipped from `default_pricing.json`). Staleness is checked at startup — warns if >30 days old.
- Config at `~/.credclaude/config.json`. Keys: `billing_day`, `daily_budget_usd`, `warn_at_pct`, `notifications_enabled`, `plan_tier`, `auto_reauth_enabled` (bool, default `true`), `auto_reauth_cooldown_sec` (int, default 1800).
- Limit data degrades gracefully: OAuth API → stale cache → disk snapshot (`snapshot.json`) → plan-tier estimator → offline state.

## Open issues / gaps
- Not cross-platform; depends on macOS `launchd`, `osascript`, and Keychain.
- App bundle is tied to source repo path; moving the repo requires re-running `install.sh`.
- No signed/notarized distribution; Gatekeeper may prompt on first launch.

## Recommended next steps
- Add pricing update workflow or auto-fetch from Anthropic's public docs.
- Consider signed/notarized packaging if distributing beyond personal use.
- Add `install.sh --check` preflight mode for dependency and launchd validation.
