# 13 Prompt Context

## Purpose
Provide reusable AI-agent context and an updated prompt template for future repo work.

## Status
- [Confirmed from code] Context below is aligned to a local macOS Python utility at v1.0.0, fully packaged as `credclaude/`.
- [Strongly inferred] Using this prompt will reduce incorrect "web-stack" or "single-file script" assumptions.

## Confirmed from code
- App type: local macOS menu bar monitor using Python + `rumps`, built as `credclaude/` package. Hidden from Dock/CMD+Tab via `NSApplicationActivationPolicyAccessory`.
- Modules: `app.py`, `auth_launcher.py`, `billing.py`, `config.py`, `cost_engine.py`, `icon_assets.py`, `ingestion.py`, `limit_providers.py`, `models.py`, `notifications.py`, `settings.py`, `time_utils.py`, `__main__.py`.
- Data sources: OAuth API (`https://api.anthropic.com/api/oauth/usage`) for session limits; JSONL files at `~/.claude/projects` for spend.
- Deployment: `.app` bundle in `~/Applications` launched by `launchd` login item (`install.sh`, `build_app.sh`).
- Persistence: local config, pricing, snapshot, and lock files in `~/.credclaude/` (`credclaude/config.py`, `credclaude/limit_providers.py`).
- Tests: `tests/` directory with ~200 test cases covering all core modules.

## Design and architecture rules to preserve
- Keep UI native/simple (menu bar + minimal modal dialogs via `rumps`).
- Avoid adding remote dependencies unless explicitly requested.
- Prioritize trust in cost numbers: pricing freshness, math correctness, parse transparency.
- Maintain install/uninstall operability via `install.sh` / `uninstall.sh`.
- Graceful degradation order: OAuth API → stale cache → disk snapshot → estimator → offline.

## Known weak points future agents should protect
- JSONL skipped-record count not surfaced to the user.
- No version/about entry or diagnostics view in the menu.
- App bundle path baked in at build time — re-run `install.sh` if repo moves.
- `KeepAlive: false` — launchd won't auto-restart on crash.
- Auto re-auth via `ReauthGate`/`launch_claude_auth_login()` requires macOS Automation permission for Terminal; blocked permissions produce an error message but do not crash the app.

## Updated reusable prompt (project-specific)
```text
You are working inside the CredClaude repository (v1.0.0).

Project reality:
- This is a local macOS menu bar app written in Python using rumps.
- Code lives in the `credclaude/` package (app.py, auth_launcher.py, billing.py, config.py,
  cost_engine.py, icon_assets.py, ingestion.py, limit_providers.py, models.py, notifications.py,
  settings.py, time_utils.py, __main__.py).
- The deprecated `monitor.py` is the old single-file version — do NOT treat it as current.
- Data: OAuth API (session utilization) + JSONL files in ~/.claude/projects (spend).
- Deployed as a .app bundle in ~/Applications via install.sh / build_app.sh / launchd.

Instructions:
1) Ground every claim in existing code before proposing changes. Reference the credclaude/ package, not monitor.py.
2) Do not assume web routes, React components, backend APIs, auth, or databases.
3) Prefer local-first, low-complexity solutions that improve reliability, debuggability, and accuracy.
4) When uncertain, label statements as: Confirmed from code / Strongly inferred / Not found in repository.
5) Preserve current behavior unless a change request explicitly asks otherwise.
6) When proposing enhancements, prioritize:
   - user-visible observability (skipped records, last sync, diagnostics)
   - pricing freshness strategy
   - test coverage for cost/date logic
   - deployment robustness on macOS
7) Keep outputs concise, practical, and repository-specific.
```

## Open issues / gaps
- No formal CONTRIBUTING or AGENTS.md policy file.
- Prompt should be revisited if web/backend is introduced or app is distributed beyond personal use.
