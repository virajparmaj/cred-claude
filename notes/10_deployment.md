# 10 Deployment

## Purpose
Describe how this project is deployed and operated in its current local-app form.

## Status
- [Confirmed from code] Deployment target is local macOS user session via `launchd`.
- [Not found in repository] No cloud deployment manifest (Vercel/Netlify/Render/Docker).

## Confirmed from code
- Install script writes `~/Library/LaunchAgents/com.veer.credclaude.plist` (`install.sh:10-11`, `install.sh:33-61`).
- Launch agent runs `venv/bin/python monitor.py` with `RunAtLoad` and `KeepAlive` enabled (`install.sh:42-53`).
- Standard output/error logs go to `~/.credclaude/monitor.log` and `.err` (`install.sh:54-58`).
- Script reloads existing agent if already present (`install.sh:64-68`).

## Inferred / proposed
- [Strongly inferred] Environment separation (dev/stage/prod) is not applicable in current single-user local model.
- [Not found in repository] No signed app bundle, notarization, installer package, or auto-update pipeline.

## Important details
- Release sequence today:
  1. Pull/update repo.
  2. Re-run `bash install.sh` to refresh env and launch agent.
  3. Verify logs in `~/.credclaude/`.
- Coupling: monitor runtime depends on local Claude log format and path conventions.

## Open issues / gaps
- No versioned release artifacts; updates are manual.
- No healthcheck command to verify launch agent status post-install.
- No rollback mechanism other than manual script rerun or uninstall.

## Recommended next steps
- Add explicit release checklist and changelog discipline.
- Add `install.sh --check` mode for dependency and launchd validation.
- Consider packaging into a signed macOS app if broader distribution is planned.
