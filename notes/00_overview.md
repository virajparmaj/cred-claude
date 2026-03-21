# 00 Overview

## Purpose
Document what this repository currently is, who it serves, and how close it is to the intended production level.

## Status
- [Confirmed from code] Functional local macOS menu bar utility with install/uninstall scripts.
- [Strongly inferred] Mature MVP for personal use, not yet hardened for broad distribution.

## Confirmed from code
- The app is a Python `rumps` menu bar app that tracks Claude usage cost from local JSONL session files (`monitor.py:1-5`, `monitor.py:378-411`).
- It scans `~/.claude/projects/**.jsonl` and subagent logs, computes token-based USD cost, and shows daily plus billing-period totals (`monitor.py:21-24`, `monitor.py:161-273`, `monitor.py:469-527`).
- It includes first-run setup for billing reset day and daily budget (`monitor.py:417-453`).
- It shows macOS notifications for billing reset day and budget threshold (`monitor.py:353-371`, `monitor.py:537-567`).
- Installation uses `launchd` for auto-start at login and writes logs to `~/.credclaude/` (`install.sh:29-75`).
- Uninstall unloads/removes the launch agent plist (`uninstall.sh:4-17`).

## Inferred / proposed
- [Strongly inferred] Primary user is an individual Claude Code power user who wants quick budget visibility without opening dashboards.
- [Strongly inferred] The intended quality bar is a reliable always-on personal observability tool for daily usage control.
- [Not found in repository] No web frontend, backend server, authentication layer, database, or cloud deployment stack.

## Important details
- Core journey: install -> app auto-starts -> first-run prompts -> passive monitoring in menu bar -> optional settings updates.
- Cost model uses hardcoded per-million-token rates for Opus/Sonnet/Haiku and defaults unknown models to Sonnet pricing (`monitor.py:34-53`, `monitor.py:115-127`).
- Config is persisted locally in `~/.credclaude/config.json` (`monitor.py:22-23`, `monitor.py:88-109`).

## Open issues / gaps
- Price table can drift from real provider pricing over time.
- Error handling is mostly silent (`except Exception: continue/pass`), reducing debuggability.
- No automated tests or CI checks.
- Not cross-platform; depends on macOS `launchd` and `osascript`.

## Recommended next steps
- Add pricing update strategy and explicit versioning for rate tables.
- Add structured logging and error counters for skipped files/lines.
- Add unit tests for parsing, cost math, and billing-date boundary logic.
- Add packaging/release notes for safer upgrades.
