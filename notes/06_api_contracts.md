# 06 API Contracts

## Purpose
Document data contracts and integration boundaries used by the app.

## Status
- [Confirmed from code] No network API exists; all contracts are local file and function contracts.
- [Not found in repository] No backend endpoints to document.

## Confirmed from code
- Input contract (session line): JSON object with `type == "assistant"`, `timestamp`, and `message.usage` + `message.model` (`monitor.py:222-229`).
- Usage keys expected: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` (`monitor.py:128-131`).
- Date parsing contract: ISO8601 timestamp, with `Z` normalized to UTC offset (`monitor.py:148-153`).
- Cost computation contract: per-million-token rate map by model family, fallback family `sonnet` (`monitor.py:115-127`, `monitor.py:133-145`).
- Config contract at `~/.credclaude/config.json`:
  - `billing_day` (1-28)
  - `daily_budget_usd` (>0)
  - `warn_at_pct` (1-100)
  - `notifications_enabled` (bool)
  (`monitor.py:55-60`, `monitor.py:580-627`)

## Inferred / proposed
- [Strongly inferred] Timeout/loading expectation: menu refresh every 300s, notification checks every 1800s (`monitor.py:28-29`).
- [Strongly inferred] Error behavior: malformed lines and parsing failures are skipped silently.
- [Not found in repository] No HTTP status codes, request auth, rate-limits, or retry policies because there is no remote API.

## Important details
- Contract strictness is low: missing fields are treated as non-fatal and ignored.
- Notification side effect contract is one-off per day via lock files (`monitor.py:363-371`, `monitor.py:546-567`).
- Current API surface is internal Python functions, not service interfaces.

## Open issues / gaps
- Contract validation is implicit; no schema validation layer.
- No user-facing indication when many records are skipped.
- No backward-compatibility versioning for potential future log format changes.

## Recommended next steps
- Add optional strict mode with schema checks and warning counters.
- Emit "last successful scan" and "records skipped" diagnostics in UI/logs.
- If future remote service is introduced, define explicit JSON schema/versioning from day one.
