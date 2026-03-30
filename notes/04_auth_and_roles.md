# 04 Auth and Roles

## Status: OAuth Dependency (Read-Only)

This is a single-user local macOS menu bar app. There is no authentication layer for the app itself, but it depends on an OAuth token managed by Claude Code.

### OAuth Token Dependency

- The app reads the OAuth credential JSON from the **macOS Keychain** (service: `Claude Code-credentials`).
- This entry is written by Claude Code when the user runs `claude auth login`.
- The Keychain JSON contains: `accessToken`, `refreshToken`, `expiresAt` (ms), `scopes`, `subscriptionType`, `rateLimitTier`.
- The `accessToken` is used to call `https://api.anthropic.com/api/oauth/usage` to fetch real session utilization data.

### Token Lifecycle

1. **Valid token**: App fetches live usage data (utilization %, reset time) from the OAuth API.
2. **Token near expiry (proactive)**: If `expiresAt` is within 10 minutes, the app calls the OAuth refresh endpoint before making the usage API call. No user action needed.
3. **Expired token (HTTP 401)**: App attempts a silent refresh using the stored `refreshToken`. If successful, retries the usage fetch immediately. If refresh also fails, enters a 5-minute cooldown and shows `"Token expired — run: claude auth login"`.
4. **Rate limited (HTTP 429)**: App backs off exponentially (120s → 300s → 600s). Last known data is shown during backoff.
5. **No token (fresh install)**: App falls back to the Estimator provider, which shows plan-tier budget estimates with LOW confidence. The menu prompts the user to run `claude auth login`.

### Token Refresh Details

- **Refresh endpoint**: `POST https://platform.claude.com/v1/oauth/token`
- **Client ID**: `9d1c250a-e61b-44d9-88ed-5944d1962f5e` (public client, no secret needed)
- **Parameters**: `grant_type=refresh_token`, `refresh_token=<token>`, `client_id=<id>`
- After a successful refresh, the Keychain entry is updated with the new `accessToken`, `refreshToken`, and `expiresAt`.
- The `refreshToken` itself expires on Anthropic's server side (typically weeks/months). Only when it expires will the user need to run `claude auth login` again.

### Re-authentication (when truly needed)

If the refresh token itself has expired, the app shows "Token expired" and the user must:

1. Open a terminal
2. Run `claude auth login`
3. Click "Refresh Now" in the menu bar (or wait for the next automatic refresh)

### Security Notes

- The app reads and writes the OAuth credential entry in the macOS Keychain (service: `Claude Code-credentials`).
- It writes only on successful token refresh, preserving all existing fields.
- All API calls use HTTPS with Bearer token authentication.
