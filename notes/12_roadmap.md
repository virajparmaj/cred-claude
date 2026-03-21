# 12 Roadmap

## Purpose
Define a practical, repo-specific hardening roadmap for this local macOS app.

## Status
- [Strongly inferred] The best path is incremental hardening, not architecture replacement.

## Confirmed from code
- Core app loop, settings flow, notifications, and launchd deployment are already in place (`monitor.py`, `install.sh`, `uninstall.sh`).

## Inferred / proposed
### Immediate fixes (next 1-2 iterations)
- [Strongly inferred] Add visible diagnostics: scanned files, skipped records, last successful scan.
- [Strongly inferred] Add settings toggle for `notifications_enabled`.
- [Strongly inferred] Fix uninstall output path text mismatch.
- [Strongly inferred] Remove dead constants and tighten exception handling paths.

### Short-term improvements
- [Strongly inferred] Add unit tests for:
  - timestamp parsing and timezone conversion,
  - cost computation,
  - billing period/reset boundaries,
  - settings validation behavior.
- [Strongly inferred] Add lightweight README for setup/use/troubleshooting.
- [Strongly inferred] Add optional CSV export for daily/billing summaries.

### Medium-term improvements
- [Strongly inferred] Externalize pricing data to a versioned local config file with update date.
- [Strongly inferred] Add richer detail window for historical trends and per-model drilldown.
- [Strongly inferred] Improve performance for period scans on large datasets.

### Long-term enhancements
- [Strongly inferred] Package as signed/notarized macOS app with clearer release channel.
- [Strongly inferred] Add safe auto-update workflow.
- [Not found in repository] Cross-platform support only if product direction changes.

## Important details
- Keep local-first architecture unless user requirements change.
- Preserve zero-cloud dependency for privacy and simplicity.

## Open issues / gaps
- No explicit acceptance criteria exist for "production ready" hardening.
- No release governance process is documented.

## Recommended next steps
- Define a v1.0 hardening checklist with measurable pass/fail criteria.
- Implement immediate fixes before adding new feature surface.
