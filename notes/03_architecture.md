# 03 Architecture

## Purpose
Explain the technical architecture, runtime boundaries, and data flow in this repository.

## Status
- [Confirmed from code] Single-process local desktop utility architecture.
- [Not found in repository] No server tier, database tier, or external auth tier.

## Confirmed from code
- Frontend/runtime stack: Python + `rumps` menu bar app (`requirements.txt:1`, `monitor.py:16`, `monitor.py:378-411`).
- Background scheduling via in-process timers for refresh and notification checks (`monitor.py:28-29`, `monitor.py:410-411`).
- Local file data source: Claude session JSONL files under `~/.claude/projects` (`monitor.py:21-24`, `monitor.py:161-170`).
- State management: local JSON config + in-memory cache (`monitor.py:55-60`, `monitor.py:88-109`, `monitor.py:382-383`, `monitor.py:193-209`).
- Notification integration: macOS `osascript` subprocess (`monitor.py:353-360`).
- Deployment/hosting model: local launch agent via `launchd` (`install.sh:29-69`).

## Inferred / proposed
- [Strongly inferred] Architecture goal is "always-on local observer" rather than online service.
- [Not found in repository] No HTTP API boundary, RPC transport, queue, or cloud secret management.
- [Not found in repository] No ML inference backend or external model-serving dependency.

## Important details
- Data flow: read JSONL -> filter assistant entries by date -> compute costs -> aggregate by model -> update menu UI.
- Resilience strategy currently favors availability over strict error visibility (broad exception catches).
- Billing period logic handles month boundaries with day clamping (`monitor.py:296-312`).

```text
[Claude local logs ~/.claude/projects/*.jsonl]
                |
                v
       [monitor.py scanner]
                |
                v
     [cost aggregation + cache]
                |
      +---------+---------+
      |                   |
      v                   v
 [menu bar text UI]   [osascript notifications]
                |
                v
 [launchd auto-start + local logs/config]
```

## Open issues / gaps
- No observability for scan failures, malformed records, or stale data.
- Cost model updates require manual code edits.
- No packaging/versioning strategy for reproducible rollouts.

## Recommended next steps
- Introduce structured logging with counters for parse failures.
- Externalize pricing config with explicit update date metadata.
- Add test harness around scanner and billing period helpers.
