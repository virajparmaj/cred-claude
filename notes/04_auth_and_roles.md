# 04 Auth and Roles

## Status: OAuth Dependency (Read-Only)

This is a single-user local macOS menu bar app. There is no authentication layer for the app itself, but it depends on an OAuth token managed by Claude Code.

### OAuth Token Dependency

- The app reads an OAuth access token from the **macOS Keychain** (service: `Claude Code-credentials`).
- This token is set by Claude Code when the user runs `claude auth login`.
- The app **never writes** to the Keychain — it only reads the token placed there by Claude Code.
- The token is used to call `https://api.anthropic.com/api/oauth/usage` to fetch real session utilization data.

### Token Lifecycle

1. **Valid token**: App fetches live usage data (utilization %, reset time) from the OAuth API.
2. **Expired token (HTTP 401)**: App enters a 5-minute cooldown. The menu shows the last known usage data marked "(stale)" and displays: `"Token expired — run: claude auth login"`.
3. **Rate limited (HTTP 429)**: App backs off exponentially (120s → 300s → 600s). Last known data is shown during backoff.
4. **No token (fresh install)**: App falls back to the Estimator provider, which shows plan-tier budget estimates with LOW confidence. The menu prompts the user to run `claude auth login`.

### Re-authentication

If the app shows "Token expired", the user must:

1. Open a terminal
2. Run `claude auth login`
3. Click "Refresh Now" in the menu bar (or wait for the next automatic refresh)

The app cannot refresh the token itself — only Claude Code can do that.

### Security Notes

- No secrets are stored by this app. The OAuth token is managed entirely by Claude Code via macOS Keychain.
- All API calls use HTTPS with Bearer token authentication.
- The token is never logged or persisted to disk by this app.
