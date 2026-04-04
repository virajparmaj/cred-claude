# 09 Dev Setup

## Purpose
Provide practical setup/run instructions for contributors.

## Status
- [Confirmed from code] Setup is script-driven with proper Python packaging.
- [Strongly inferred] macOS is required for full runtime behavior (Keychain, osascript, launchd).

## Confirmed from code
- **Dependencies**: `rumps>=0.4.0` + `pyobjc-framework-Cocoa` (`pyproject.toml` / `requirements.txt`).
- **Packaging**: `pyproject.toml` (metadata, dynamic version from `credclaude/__init__.py`). `setup.py` is a minimal shim.
- **Entry point**: `python -m credclaude` (via `credclaude/__main__.py`).
- **Install script**: `install.sh` — creates venv, `pip install -e .`, builds `.app` via `build_app.sh`, copies to `~/Applications`, registers launchd.
- **Uninstall script**: `uninstall.sh` — unloads/removes launch agent plist, optionally removes `.app`.
- **Tests**: `tests/` directory with 10 test modules covering billing, config, cost_engine, formatting, ingestion, limit_providers, app, auth_launcher, icon_assets, and conftest. Run with `pytest`.
- Local data at `~/.credclaude/`. Claude logs expected at `~/.claude/projects/`.

## Dev run commands
```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .

# Run directly (no .app bundle needed for dev)
python -m credclaude

# Run tests
pytest tests/ -v

# Build + install as .app
bash install.sh

# Remove login item
bash uninstall.sh
```

## Important details
- Python 3.11+ required (3.14 used in current dev venv). No strict minor version pinned.
- `build_app.sh` reads version from `credclaude/__init__.py` — single source of truth.
- `build_app.sh` builds `dist/CredClaude.app` using a shell launcher script wrapping `python -m credclaude`. Includes icon resources built from the tracked `assets/icons/macos/` sources.
- App logs go to `~/.credclaude/monitor.log` (RotatingFileHandler, not captured by launchd).
- No `.env` or environment variable parsing in application code.

## Open issues / gaps
- No formatter or lint config committed (`black`, `isort`, `mypy` not configured in `pyproject.toml`).
- Script does not verify required macOS tools (`launchctl`, `osascript`, `sips`, `iconutil`) before install.
- No README with contributor workflow and troubleshooting.

## Recommended next steps
- Add `black`/`isort`/`mypy` config to `pyproject.toml`.
- Add preflight checks in `install.sh` for required macOS tools.
- Add README with quickstart, troubleshooting, and upgrade notes.
