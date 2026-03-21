# 13 Prompt Context

## Purpose
Provide reusable AI-agent context and an updated prompt template for future repo work.

## Status
- [Confirmed from code] Context below is aligned to a local macOS Python utility, not a web app.
- [Strongly inferred] Using this prompt will reduce incorrect "web-stack" assumptions.

## Confirmed from code
- App type: local macOS menu bar monitor using Python + `rumps` (`monitor.py:16`, `monitor.py:378-411`).
- Data source: local Claude session JSONL files in `~/.claude/projects` (`monitor.py:21-24`, `monitor.py:161-170`).
- Deployment: local `launchd` agent (`install.sh:29-69`).
- Persistence: local config and lock files in `~/.credclaude` (`monitor.py:22-26`, `monitor.py:363-371`).

## Inferred / proposed
- [Strongly inferred] Non-negotiable goal: keep app reliable, accurate, local-first, and low-friction.
- [Not found in repository] No backend/auth/database expectations unless future scope explicitly changes.

## Important details
### Design and architecture rules to preserve
- Keep UI native/simple (menu bar plus minimal modal dialogs).
- Avoid adding remote dependencies unless explicitly requested.
- Prioritize trust in cost numbers (math correctness, pricing freshness, parsing transparency).
- Maintain install/uninstall operability with launchd.

### Known weak points future agents should protect
- Silent exception paths hide failures.
- Hardcoded model pricing can drift.
- Missing tests around date and cost logic.
- Settings UX lacks full control/validation feedback.

### Updated reusable prompt (project-specific)
```text
You are working inside the CredClaude repository.

Project reality:
- This is a local macOS menu bar app written in Python using rumps.
- It reads Claude session JSONL files from ~/.claude/projects and computes daily/billing-period usage cost.
- It is deployed locally via launchd (install.sh/uninstall.sh), not via web/cloud services.

Instructions:
1) Ground every claim in existing code and scripts before proposing changes.
2) Do not assume web routes, React components, backend APIs, auth, or databases unless explicitly added in this repo.
3) Prefer local-first, low-complexity solutions that improve reliability, debuggability, and accuracy.
4) When uncertain, label statements as:
   - Confirmed from code
   - Strongly inferred
   - Not found in repository
5) If documenting or refactoring, preserve current behavior unless a change request explicitly asks otherwise.
6) If proposing enhancements, prioritize:
   - parse/error visibility
   - pricing freshness strategy
   - test coverage for cost/date logic
   - setup/deployment robustness on macOS
7) Keep outputs concise, practical, and repository-specific.
```

## Open issues / gaps
- [Not found in repository] No formal CONTRIBUTING or agent policy file yet.
- [Strongly inferred] Prompt should be revisited when architecture changes (for example, if web/backend is introduced).

## Recommended next steps
- Copy this prompt into future task briefs for consistent execution quality.
- Add `README.md` and optionally `AGENTS.md` to codify these rules in-repo.
