# 01 Features

## Purpose
Catalog implemented and missing capabilities with direct code evidence.

## Status
- [Confirmed from code] Core monitoring loop works end-to-end. OAuth API provides live session data; JSONL scanning provides spend data.
- [Confirmed from code] All previously-pending hardening items shipped in v1.0.0 refactor.

## Confirmed from code
- **Live session utilization** from OAuth API (`credclaude/limit_providers.py`): 5-hour window %, reset time, last sync timestamp.
- **Daily cost computation** from JSONL assistant messages with token usage parsing (`credclaude/ingestion.py`, `credclaude/cost_engine.py`).
- **Model-family breakdown** (Opus/Sonnet/Haiku/Claude 4.x) in menu lines (`credclaude/cost_engine.py`).
- **Billing-period total and reset countdown** (`credclaude/billing.py`).
- **Progress bar** visualization in menu (text glyph, `credclaude/app.py`).
- **First-run setup wizard** for billing day, budget, and plan tier (`credclaude/app.py`).
- **Editable settings** for billing day, daily budget, warning threshold, notifications on/off, plan tier (`credclaude/app.py`).
- **Notification system** for reset day and budget threshold (`credclaude/notifications.py`).
- **Install/uninstall** with `.app` bundle build and launchd registration (`install.sh`, `build_app.sh`, `uninstall.sh`).
- **Notifications toggle** in settings UI — fully implemented.
- **Externalized pricing** to `~/.credclaude/pricing.json` with staleness check.
- **Automatic OAuth token refresh**: proactive refresh when token expires within 10 minutes; silent reactive refresh on HTTP 401 before entering cooldown (`credclaude/limit_providers.py`).
- **Plan tier estimator** fallback with LOW-confidence community estimates when OAuth is unavailable.
- **Graceful degradation**: OAuth (with auto-refresh) → stale cache → disk snapshot → estimator → offline.
- **Weekly utilization** from OAuth API `seven_day` key: weekly %, reset date+time shown as "Apr 7 at 12:00 AM". Hidden for accounts without a weekly cap (`credclaude/limit_providers.py`, `credclaude/app.py`).
- **Extra usage** from OAuth API `extra_usage` key: shown as bar + % when `extra_usage_enabled` is true, with monthly dollar amounts when available (`credclaude/limit_providers.py`, `credclaude/app.py`).
- **Auto re-auth**: On each update cycle, if `LimitInfo.error` indicates an auth error, `ReauthGate` (30-min cooldown) auto-triggers `launch_claude_auth_login()` to open Terminal and run `claude auth login`. Manual "Re-authenticate" menu item also available. Controlled by `auto_reauth_enabled` config key (`credclaude/auth_launcher.py`, `credclaude/app.py`).
- **Dock-hidden operation**: App sets `NSApplicationActivationPolicyAccessory` at startup — does not appear in Dock or CMD+Tab (`credclaude/app.py`).
- **Icon assets**: Dedicated menu bar icon (`assets/credclaude_menubar.png`) and runtime/dock icon (`.app` bundle resources or repo fallback PNGs) managed by `credclaude/icon_assets.py`.

## Inferred / proposed
- [Not found in repository] **Not implemented**: Historical trend view (weekly/monthly charts) and CSV export.
- [Not found in repository] **Not implemented**: Per-project cost filtering or include/exclude rules.
- [Not found in repository] **Not implemented**: Signed/notarized distribution or auto-update.

## Important details
- Feature scope is local-first: JSONL scanning for spend, OAuth API for session limits.
- Pricing freshness is actively managed; staleness warnings shown at startup.
- Caching exists for unchanged JSONL files by size (`credclaude/ingestion.py`).

## Open issues / gaps
- No self-diagnostics screen showing scanned files, skipped entries, or last scan time.
- No historical summaries or export capability.
- Weekly utilization is now shown when the API exposes it; weekly cap is not independently computed locally.

## Recommended next steps
- Add a "Data health" section showing scanned files, skipped entries, and last scan time.
- Add optional 7-day or billing-period spend chart/export.
