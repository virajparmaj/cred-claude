# 08 Pages And Routes

## Purpose
Map interaction surfaces for this project (menu-based desktop app, not route-based web app).

## Status
- [Confirmed from code] No HTTP or frontend router exists.
- [Strongly inferred] Equivalent route map is menu/window action map.

## Confirmed from code
| Route/path equivalent | Purpose | Auth needed? | Primary components | Data dependencies | Current status |
|---|---|---|---|---|---|
| Menu bar title | Session utilization % + reset countdown | No | `rumps.App.title` | OAuth `LimitInfo` | Implemented |
| `session_line` menu item | 5-hour window % with confidence indicator | No | `rumps.MenuItem` | `LimitInfo.utilization_pct`, `Confidence` | Implemented |
| `resets_at_line` menu item | Time until next session reset | No | `rumps.MenuItem` | `LimitInfo.resets_at` | Implemented |
| `daily_summary` menu item | Daily spend vs budget | No | `rumps.MenuItem` | `CostData.total_cost`, config budget | Implemented |
| `progress_bar` menu item | Visual usage percentage bar | No | text bar glyph | Percent budget used | Implemented |
| `model_lines` menu items | Model family cost/token breakdown | No | dynamic menu labels | per-family aggregation | Implemented |
| `period_total` menu item | Billing-period total | No | dynamic menu label | period scan totals | Implemented |
| `billing_reset` menu item | Time to next billing reset | No | dynamic menu label | countdown helper | Implemented |
| `last_sync` menu item | Timestamp of last successful OAuth sync | No | dynamic menu label | `LimitInfo.last_sync` | Implemented |
| `weekly_bar_item` menu item | 7-day window utilization % bar | No | dynamic menu label | `LimitInfo.weekly_utilization_pct` | Implemented (hidden if API returns no weekly data) |
| `weekly_reset_item` menu item | Date+time of next 7-day window reset | No | dynamic menu label | `LimitInfo.weekly_resets_at` | Implemented (hidden if API returns no weekly data) |
| `extra_usage_item` menu item | Extra (add-on) usage bar or dollar amounts | No | dynamic menu label | `LimitInfo.extra_usage_*` | Implemented (hidden if `extra_usage_enabled` is false/None) |
| `Settings` action | Multi-step settings dialogs | No | AppKit native window (`settings.py`) | config values | Implemented |
| `Refresh Now` action | Force immediate refresh | No | callback | clears backoff + reloads | Implemented |
| `Re-authenticate` action | Manually trigger `claude auth login` in Terminal | No | `auth_launcher.launch_claude_auth_login()` | none | Implemented |
| `Quit` action | Exit app process | No | `rumps.quit_application` | none | Implemented |

## Inferred / proposed
- [Not found in repository] No URL routes (`/`, `/dashboard`, `/api/*`).
- [Strongly inferred] A detail/analytics window could serve as a "page" equivalent if historical data is added.

## Important details
- Route protection is not applicable for current local single-user mode.
- Data dependency is OAuth API + local JSONL files + in-memory state.

## Open issues / gaps
- No version/about view for supportability.
- No dedicated troubleshooting or diagnostics view.
- No "Open logs folder" menu entry.

## Recommended next steps
- Add menu entries for version info (`v1.0.0`) and "Open logs folder".
- Add optional detailed stats window for historical trends.
