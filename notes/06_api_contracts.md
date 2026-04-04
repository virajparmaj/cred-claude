# 06 API Contracts

## Purpose
Document data contracts and integration boundaries used by the app.

## Status
- [Confirmed from code] One external HTTP API (OAuth usage endpoint). All other contracts are local file and function contracts.

## External API: OAuth Usage Endpoint

- **URL**: `https://api.anthropic.com/api/oauth/usage`
- **Method**: GET
- **Auth**: Bearer token from macOS Keychain (`Claude Code-credentials`)
- **Beta header**: `anthropic-beta: oauth-2025-04-20`
- **Response fields used**:
  - `utilization` — float, fraction format (0.0–1.0); normalized to 0–100% by `_normalize_utilization()`
  - `resets_at` — ISO8601 timestamp for next 5-hour window reset
  - `seven_day.utilization` — float (0.0–1.0); weekly utilization %. `None` for accounts without a weekly cap.
  - `seven_day.resets_at` — ISO8601 timestamp for next 7-day window reset; parsed with 8-day max-future guard (`_WEEKLY_RESET_MAX_FUTURE_SEC`).
  - `extra_usage.enabled` — bool; whether extra (add-on) usage is active.
  - `extra_usage.monthly_limit` — float; monthly dollar cap for extra usage.
  - `extra_usage.used` — float; dollars used toward extra usage this month.
  - `extra_usage.utilization` — float (0.0–1.0); fraction of extra usage cap consumed.
- **Error handling**:
  - HTTP 401 → token expired; 5-min cooldown, menu shows "(stale)" + `"Token expired — run: claude auth login"`
  - HTTP 429 → rate limited; exponential backoff `[120, 300, 600]`s; last known data shown during backoff
  - Network error → falls back to disk snapshot → estimator
- **Rate**: 60s poll interval (60 calls/hour). Startup call deferred 5s to avoid hammering on iterative installs.

## Local File Contracts

- **JSONL session line**: JSON object with `type == "assistant"`, `timestamp` (ISO8601), `message.usage`, `message.model`.
  - Usage keys: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` (`credclaude/ingestion.py`).
- **Config** (`~/.credclaude/config.json`):
  - `billing_day` (int, 1–28)
  - `daily_budget_usd` (float, >0)
  - `warn_at_pct` (int/float, 1–100)
  - `notifications_enabled` (bool)
  - `plan_tier` (str: `"pro"` | `"max_5x"` | `"max_20x"`)
  - Type-validated on load; invalid fields reset to defaults (`credclaude/config.py`).
- **Pricing** (`~/.credclaude/pricing.json`): model-family rate map with `updated_at` field; staleness-checked at startup.
- **Snapshot** (`~/.credclaude/snapshot.json`): last successful `LimitInfo` serialized to JSON.

## Inferred / proposed
- [Strongly inferred] Refresh interval (60s) and backoff steps are tunable via constants in `credclaude/config.py` and `credclaude/limit_providers.py`.

## Important details
- JSONL contract strictness is low: missing fields are non-fatal and skipped with `logger.debug()`.
- Notification dedup contract: one lock file per day per notification type.
- `_normalize_utilization`: value ≤ 1.0 → multiply by 100; value > 1.0 → pass through (future-proofing). Edge case: 1.0 = 100%, not 1%.

## Open issues / gaps
- No schema validation layer on JSONL; malformed records are skipped silently (but logged at debug level).
- No user-visible count of skipped records.
- No backward-compatibility versioning for potential future log format changes.

## Recommended next steps
- Emit "records skipped" count in UI or structured log.
- If the OAuth API adds new fields, add them to `LimitInfo` and the snapshot schema.
