# 03 Architecture

## Purpose
Explain the technical architecture, runtime boundaries, and data flow in this repository.

## Status
- [Confirmed from code] Single-process local desktop utility architecture, fully refactored into `credclaude/` package at v1.0.0.
- [Not found in repository] No server tier, database tier, or external auth tier.

## Confirmed from code
- **Runtime stack**: Python + `rumps` menu bar app, run as a built `.app` bundle (`build_app.sh`, `install.sh`).
- **Entry point**: `credclaude/__main__.py` → acquires PID lock (atomic `fcntl.flock`) → configures logging → starts `CredClaude` app.
- **Package modules**:
  - `app.py` — `rumps.App` subclass; menu construction, update cycle, first-run wizard; delegates settings UI to `settings.py`.
  - `billing.py` — billing period boundaries, reset-day clamping.
  - `config.py` — config load/save/validate, `APP_DIR`, logging setup, `default_pricing.json` copy.
  - `cost_engine.py` — per-model token cost calculation, pricing table management.
  - `ingestion.py` — JSONL file scanning, session log parsing, file-size cache.
  - `limit_providers.py` — `OfficialLimitProvider` (OAuth API + retry guard), `EstimatorProvider` (plan-tier fallback), `CompositeLimitProvider` (orchestration + disk snapshot).
  - `models.py` — shared dataclasses: `LimitInfo`, `WindowInfo`, `CostData`, `Confidence`, `ProviderState`.
  - `notifications.py` — macOS `osascript` notification dispatch, lock-file dedup.
  - `settings.py` — native macOS settings window built with AppKit/objc; replaces the old sequential rumps dialog chain.
- **Background scheduling**: two in-process `rumps` timers — refresh (60s) + startup one-shot (5s delay).
- **OAuth data source**: `https://api.anthropic.com/api/oauth/usage` — reads/writes token from macOS Keychain (service: `Claude Code-credentials`). Token refresh via `POST https://platform.claude.com/v1/oauth/token` (public client `9d1c250a-e61b-44d9-88ed-5944d1962f5e`); Keychain entry updated on successful refresh.
- **JSONL data source**: `~/.claude/projects/*/*.jsonl` and subagent logs — read-only.
- **State management**: local JSON config + in-memory cache + disk snapshot (`~/.credclaude/snapshot.json`).
- **Notification integration**: macOS `osascript` subprocess (`credclaude/notifications.py`).
- **Deployment**: `.app` bundle in `~/Applications`; launchd login item runs `open -a CredClaude` (`install.sh`).
- **Packaging**: `pyproject.toml` (metadata + dynamic version), `setup.py` (minimal shim), `build_app.sh` (shell `.app` builder).

## Inferred / proposed
- [Strongly inferred] Architecture goal is "always-on local observer" rather than online service.
- [Not found in repository] No HTTP API boundary, RPC transport, queue, or cloud secret management.

## Important details
- **Limit data flow**: OAuth API (utilization %, reset time) → in-memory cache → disk snapshot. On failure: stale cache → snapshot → estimator → offline.
- **Cost data flow**: read JSONL → filter assistant entries by date → compute costs via pricing table → aggregate by model → update menu UI.
- **Resilience**: narrowed exception catches with `logger.debug()` on all skip paths; single `_update()` wrapper prevents provider failure from crashing the app.
- **Rate limiting**: refresh every 60s (60 calls/hour); startup deferred 5s. `OfficialLimitProvider` tracks a local retry guard (`_retry_after`, `_retry_reason`, `_rate_limit_step`). On 429: exponential backoff via `RATE_LIMIT_BACKOFF_STEPS_SEC = (120, 300, 600)` s. On 401 (token expired): app first attempts a silent refresh via `_try_silent_refresh()` → `_refresh_oauth_token()`; if successful, retries the usage fetch immediately. Only if the silent refresh fails does it enter the fixed 5-min cooldown (`TOKEN_EXPIRED_COOLDOWN_SEC = 300`). Proactive refresh also runs before the usage call if the token's `expiresAt` is within 10 minutes (`_PROACTIVE_REFRESH_THRESHOLD_SEC = 600`). `force_refresh()` (triggered by "Refresh Now") clears `_retry_after`/`_retry_reason` to bypass the local guard but preserves `_rate_limit_step`.
- **Billing period** logic handles month boundaries with day clamping (`credclaude/billing.py`).

```text
[Keychain: Claude Code-credentials OAuth token]
                |
                v
  [OfficialLimitProvider — /api/oauth/usage]
                |
       +---------+---------+
       |                   |
   success              401/429/err
       |                   |
       v                   v
  [in-memory cache]   [EstimatorProvider (fallback)]
                |
                v
     [disk snapshot ~/.credclaude/snapshot.json]
                |
                v
[~/.claude/projects/*.jsonl — JSONL scanner]
                |
                v
   [cost aggregation (ingestion + cost_engine)]
                |
       +---------+---------+
       |                   |
       v                   v
[menu bar text UI]   [osascript notifications]
                |
                v
[launchd .app auto-start + ~/.credclaude/ logs/config]
```

## Open issues / gaps
- App bundle path is baked in at build time; moving the repo requires re-running `install.sh`.
- No signed/notarized distribution; Gatekeeper may prompt on first launch.
- No packaging/auto-update pipeline.

## Recommended next steps
- Externalize repo path from `.app` launcher script (or detect at runtime).
- Add `install.sh --check` preflight validation.
- Consider signed packaging if distributing beyond personal use.
