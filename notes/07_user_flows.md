# 07 User Flows

## Purpose
Describe real end-user flows and where they are complete or incomplete.

## Status
- [Confirmed from code] Main local flows are implemented for setup, monitoring, settings, and notifications.
- [Strongly inferred] Some maintenance and troubleshooting flows are incomplete.

## Confirmed from code
- Install and startup flow:
  1. Run `bash install.sh`.
  2. Virtual environment is created and dependency installed.
  3. Launch agent plist is created and loaded.
  4. App appears in menu bar.
  (`install.sh:17-75`)
- First-run onboarding flow:
  1. Prompt for billing reset day.
  2. Prompt for daily budget.
  3. Save config locally.
  (`monitor.py:385-389`, `monitor.py:417-453`)
- Daily monitoring flow:
  1. App scans session logs.
  2. Computes daily + period cost.
  3. Updates menu title/progress/model lines.
  (`monitor.py:469-527`)
- Settings update flow:
  1. Open Settings menu item.
  2. Update billing day, budget, warn threshold.
  3. Persist config and refresh display.
  (`monitor.py:577-631`)
- Notification flow:
  1. Every 30 minutes check reset and budget threshold.
  2. Send macOS notification if conditions met and lock not present.
  (`monitor.py:537-567`)

## Inferred / proposed
- [Not found in repository] No signup/login flow (not required for current local architecture).
- [Not found in repository] No dashboard/profile/admin flow.
- [Strongly inferred] Troubleshooting flow depends on reading raw log files; no in-app diagnostics screen.

## Important details
- "Landing" in this app is effectively the menu bar title state after launch, not a webpage.
- Core main action is passive monitoring; user interaction is mostly settings and refresh.
- Save/edit/delete applies to local config edits only; no domain objects are created/deleted.

## Open issues / gaps
- No explicit flow for missing log directory (`~/.claude/projects`) or permission problems.
- No validation feedback if user enters invalid values in settings (input is ignored silently).
- No guided recovery for corrupted config file.

## Recommended next steps
- Add user-visible status line for "data source found / not found".
- Add inline validation/error messages in settings dialogs.
- Add "Open logs" menu action for easier support.
