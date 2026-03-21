# 01 Features

## Purpose
Catalog implemented and missing capabilities with direct code evidence.

## Status
- [Confirmed from code] Core monitoring loop works end-to-end for local Claude session logs.
- [Strongly inferred] Several UX and reliability hardening items are still pending.

## Confirmed from code
- Daily cost computation from assistant messages with token usage parsing (`monitor.py:173-273`).
- Model-family breakdown (Opus/Sonnet/Haiku) in menu lines (`monitor.py:34-53`, `monitor.py:496-514`).
- Billing-period total and reset countdown (`monitor.py:280-320`, `monitor.py:516-524`).
- Progress bar visualization in menu (`monitor.py:327-331`, `monitor.py:494`).
- First-run setup wizard for billing day and budget (`monitor.py:417-453`).
- Editable settings for billing day, daily budget, warning threshold (`monitor.py:577-631`).
- Notification system for reset day and budget threshold (`monitor.py:537-567`).
- Install/uninstall scripts with launchd registration (`install.sh:17-75`, `uninstall.sh:9-17`).

## Inferred / proposed
- [Strongly inferred] **Partially implemented**: Notification preferences exist in config (`notifications_enabled`) but no UI path toggles it (`monitor.py:55-60`, `monitor.py:539-540`).
- [Strongly inferred] **Partially implemented**: Config migration suggests older message-limit behavior was replaced by budget model (`monitor.py:94-97`).
- [Not found in repository] **Not implemented but implied**: Explicit model-rate update mechanism or external pricing sync.
- [Not found in repository] **Not implemented but implied**: Historical trend view (weekly/monthly charts) and export.
- [Not found in repository] **Not implemented but implied**: Per-project filtering or include/exclude rules.
- [Strongly inferred] **Nice-to-have/future**: Cross-platform support, packaging, signed distribution.

## Important details
- Feature scope is intentionally local-only and file-driven.
- No remote API calls are required for current operation.
- Caching exists for unchanged files by size within the current day (`monitor.py:193-209`, `monitor.py:459-463`).

## Open issues / gaps
- Model-rate assumptions can become inaccurate.
- Missing toggles and discoverability for some config keys.
- No self-diagnostics screen for malformed logs or skipped records.

## Recommended next steps
- Add a settings toggle for `notifications_enabled`.
- Add a "Data health" section showing scanned files, skipped entries, and last scan time.
- Add optional historical summaries (7-day, billing-period average).
