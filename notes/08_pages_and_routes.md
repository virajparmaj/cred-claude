# 08 Pages And Routes

## Purpose
Map interaction surfaces for this project (menu-based desktop app, not route-based web app).

## Status
- [Confirmed from code] No HTTP or frontend router exists.
- [Strongly inferred] Equivalent route map is menu/window action map.

## Confirmed from code
| Route/path equivalent | Purpose | Auth needed? | Primary components | Data dependencies | Current status |
|---|---|---|---|---|---|
| Menu bar title | At-a-glance daily cost and reset countdown | No | `rumps.App.title` | Daily scan totals | Implemented |
| `daily_summary` menu item | Show daily spend vs budget | No | `rumps.MenuItem` | `today_data.total_cost`, config budget | Implemented |
| `progress_bar` menu item | Visual usage percentage bar | No | text bar from `make_bar` | Percent budget used | Implemented |
| `model_line_1..3` menu items | Model family cost/token breakdown | No | dynamic menu labels | per-family aggregation | Implemented |
| `period_total` menu item | Billing-period total | No | dynamic menu label | period scan totals | Implemented |
| `billing_reset` menu item | Time to next reset | No | dynamic menu label | countdown helper | Implemented |
| `Settings` action | Open 3-step settings edits | No | `rumps.Window` dialogs | config values | Implemented |
| `Refresh Now` action | Force immediate rescan | No | callback | clears cache + reload config | Implemented |
| `Quit` action | Exit app process | No | `rumps.quit_application` | none | Implemented |

## Inferred / proposed
- [Not found in repository] No URL routes (`/`, `/dashboard`, `/api/*`).
- [Strongly inferred] Future desktop detail window could serve as a "page" equivalent if analytics expand.

## Important details
- Route protection is not applicable for current local single-user mode.
- Data dependency is entirely local filesystem + in-memory state.

## Open issues / gaps
- No dedicated troubleshooting view.
- No "about/version" view for supportability.

## Recommended next steps
- Add menu entries for version info and diagnostics.
- Add optional detailed stats window if route-like expansion is needed.
