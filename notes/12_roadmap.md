# 12 Roadmap

## Purpose
Define a practical, repo-specific roadmap for continued improvement of this local macOS app.

## Status
- [Confirmed from code] v1.0.0 shipped: full package refactor, OAuth API integration, tests, `.app` bundle, externalized pricing, settings UI complete.
- [Strongly inferred] Next phase is polish and observability, not architecture replacement.

## Completed (shipped in v1.0.0 refactor)
- `credclaude/` package structure replacing single `monitor.py`
- OAuth API integration for live 5-hour session utilization
- Graceful degradation: OAuth → stale cache → snapshot → estimator → offline
- Externalized pricing (`~/.credclaude/pricing.json`) with staleness check
- Native macOS settings window (`credclaude/settings.py`) via AppKit/objc — replaces sequential rumps dialog chain
- Notifications toggle in settings UI
- Weekly utilization + extra usage sections in menu (hidden when API returns no data)
- Auto re-auth: `ReauthGate` + `launch_claude_auth_login()` opens Terminal automatically on auth errors
- Manual "Re-authenticate" menu item
- App hidden from Dock/CMD+Tab via `NSApplicationActivationPolicyAccessory`
- Dedicated icon assets module (`icon_assets.py`) + sharpened `@2x` menu bar icon
- Time utilities module (`time_utils.py`) with `fmt_relative()` and `fmt_datetime()`
- 10 test modules including `test_auth_launcher.py`, `test_icon_assets.py`, `test_app.py`
- Atomic PID lock (`fcntl.flock`)
- Structured logging with `RotatingFileHandler`
- Type-validated config loading
- 6 test modules (~200+ test cases) covering all core modules
- `.app` bundle build via `build_app.sh`
- `install.sh` builds, copies, and registers launchd login item
- Version single-sourced from `credclaude/__init__.py`
- Warn lock file cleanup on startup
- Local retry guard in `OfficialLimitProvider`: exponential backoff on 429; on 401 — silent token refresh attempted first, 5-min cooldown only if refresh fails; proactive refresh 10 min before expiry; "Refresh Now" bypasses guard via `force_refresh()`

## Near-term improvements
- Add "Open logs folder" menu item for easier support
- Add version/about entry in menu (`v1.0.0`)
- Add "Data health" status: scanned files, skipped entries, last scan time
- Document `launchctl list com.veer.credclaude` as healthcheck in README
- Add `black`/`isort`/`mypy` config to `pyproject.toml`
- Add preflight checks in `install.sh` (verify `osascript`, `sips`, `iconutil`)

## Medium-term improvements
- Add 7-day or billing-period spend history (in-memory or lightweight file store)
- Optional CSV export of daily/billing summaries
- Pricing auto-update workflow (or link to update instructions)
- Per-project cost breakdown option

## Long-term / if scope changes
- Signed/notarized macOS app bundle for broader distribution
- Auto-update workflow (e.g., Sparkle framework or GitHub release check)
- Cross-platform support only if product direction changes
- Historical trend window with charting

## Important details
- Keep local-first architecture; no cloud dependencies unless explicitly requested.
- Pricing freshness strategy should avoid requiring code changes for routine rate updates.

## Open issues / gaps
- No formal v1.x acceptance criteria or release checklist documented.
- No CHANGELOG or release notes file.
