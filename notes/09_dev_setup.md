# 09 Dev Setup

## Purpose
Provide practical setup/run instructions for contributors.

## Status
- [Confirmed from code] Setup is lightweight and script-driven.
- [Strongly inferred] macOS is required for full runtime behavior.

## Confirmed from code
- Dependency: `rumps>=0.4.0` (`requirements.txt:1`).
- Install script creates `venv/`, installs deps, and registers launchd agent (`install.sh:17-69`).
- Uninstall script unloads/removes launch agent (`uninstall.sh:9-17`).
- Local app files live in `~/.credclaude` (`monitor.py:22-23`, `install.sh:8`).
- No `.env` file usage or environment variable parsing in application code.

## Inferred / proposed
- [Strongly inferred] Python 3.14 was used in current local dev venv (`venv/pyvenv.cfg`), but project does not pin a strict Python minor version.
- [Strongly inferred] Recommended contributor baseline: Python 3.11+ on macOS.
- [Not found in repository] No test runner, formatter, or lint config committed.

## Important details
- Local run commands:
  - `python3 -m venv venv`
  - `source venv/bin/activate`
  - `pip install -r requirements.txt`
  - `python monitor.py`
- Install as login item: `bash install.sh`
- Remove login item: `bash uninstall.sh`
- Runtime assumptions: existing Claude logs under `~/.claude/projects`.

## Open issues / gaps
- Script does not verify required macOS tools (`launchctl`, `osascript`) before install.
- No README with contributor workflow and troubleshooting.
- Uninstall message references a different folder path than current repo location (`uninstall.sh:19`).

## Recommended next steps
- Add a README with quickstart, troubleshooting, and upgrade notes.
- Add basic preflight checks in install script for macOS dependencies.
- Add minimal test and lint commands for repeatable contributions.
