"""Limit providers — fetch session usage from the Claude OAuth API or estimate it."""

from __future__ import annotations

import datetime
import getpass
import json
import logging
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod

from credclaude.config import SNAPSHOT_PATH
from credclaude.models import Confidence, LimitInfo, ProviderState, WindowInfo

logger = logging.getLogger("credclaude.limit_providers")

# ---------------------------------------------------------------------------
# Plan tier budget estimates (community-derived, NOT official)
# ---------------------------------------------------------------------------
PLAN_ESTIMATES: dict[str, dict] = {
    "pro": {
        "daily_budget_usd": 15.0,
        "confidence": Confidence.LOW,
        "note": "Community estimate — Anthropic does not publish exact USD limits",
    },
    "max_5x": {
        "daily_budget_usd": 75.0,
        "confidence": Confidence.LOW,
        "note": "Community estimate — approximately 5x Pro",
    },
    "max_20x": {
        "daily_budget_usd": 150.0,
        "confidence": Confidence.LOW,
        "note": "Community estimate — approximately 20x Pro",
    },
}

_OAUTH_URL = "https://api.anthropic.com/api/oauth/usage"
_OAUTH_BETA = "oauth-2025-04-20"
_KEYCHAIN_SERVICE = "Claude Code-credentials"
_TOKEN_REFRESH_URL = "https://platform.claude.com/v1/oauth/token"
_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
_PROACTIVE_REFRESH_THRESHOLD_SEC = 600  # Refresh proactively if token expires within 10 min
_RESET_PAST_GRACE_SEC = 300
_RESET_MAX_FUTURE_SEC = 12 * 3600
_WEEKLY_RESET_MAX_FUTURE_SEC = 8 * 24 * 3600  # 8 days — weekly resets are ~7 days out


def _now() -> datetime.datetime:
    """Return current timezone-aware datetime (consistent across all providers)."""
    return datetime.datetime.now().astimezone()


def _parse_resets_at(
    value: str | None,
    source: str,
    max_future_sec: int = _RESET_MAX_FUTURE_SEC,
) -> tuple[datetime.datetime | None, str | None]:
    """Parse and sanitize resets_at. Returns (datetime_or_none, invalid_reason_or_none)."""
    if not value:
        return None, "missing"
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        logger.warning("%s resets_at parse failed (%r) — clearing", source, value)
        return None, "parse_error"
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    else:
        parsed = parsed.astimezone()

    delta_sec = (parsed - _now()).total_seconds()
    if delta_sec < -_RESET_PAST_GRACE_SEC:
        return None, "too_past"
    if delta_sec > max_future_sec:
        logger.warning("%s resets_at too far in future (%s) — clearing", source, parsed.isoformat())
        return None, "too_future"
    return parsed, None


def _heal_snapshot_resets_at(data: dict, reason: str) -> None:
    """Self-heal snapshot by clearing an invalid resets_at field."""
    if data.get("resets_at") is None:
        return
    try:
        healed = dict(data)
        healed["resets_at"] = None
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(json.dumps(healed))
        logger.info("Snapshot resets_at cleared (%s)", reason)
    except Exception as e:
        logger.debug("Failed to heal snapshot resets_at: %s", e)


# ---------------------------------------------------------------------------
# Utilization normalization
# ---------------------------------------------------------------------------
def _normalize_utilization(value: float) -> float:
    """Normalize utilization to 0..100 range.

    The Claude OAuth API returns utilization as a fraction (0.0–1.0).
    The <= 1.0 threshold handles this correctly: values in [0.0, 1.0] are
    multiplied by 100 to become percentages. Values > 1.0 pass through
    as-is (future-proofing for a potential API format change to percents).

    Edge case: API value 1.0 → interpreted as 100%, not 1%. This matches
    the API's documented behavior (fraction format).

    Result is clamped to [0, 100] and rounded to 1 decimal.
    """
    if value <= 1.0:
        value = value * 100
    return max(0.0, min(100.0, round(value, 1)))


# ---------------------------------------------------------------------------
# Disk snapshot — persists last successful usage across app restarts
# ---------------------------------------------------------------------------
def _save_snapshot(info: LimitInfo) -> None:
    """Persist last successful usage to disk."""
    try:
        resets_at = info.resets_at
        if resets_at is not None:
            parsed, reason = _parse_resets_at(resets_at.isoformat(), "snapshot save")
            if reason == "too_future":
                resets_at = None
            elif reason is None:
                resets_at = parsed
        weekly_resets_at = info.weekly_resets_at
        if weekly_resets_at is not None:
            parsed_w, reason_w = _parse_resets_at(
                weekly_resets_at.isoformat(), "snapshot save weekly",
                max_future_sec=_WEEKLY_RESET_MAX_FUTURE_SEC,
            )
            if reason_w is not None:
                weekly_resets_at = None
            else:
                weekly_resets_at = parsed_w
        data = {
            "utilization_pct": info.utilization_pct,
            "resets_at": resets_at.isoformat() if resets_at else None,
            "last_sync": info.last_sync.isoformat() if info.last_sync else None,
            "source": info.source,
            "saved_at": _now().isoformat(),
            # Weekly limit (nullable)
            "weekly_utilization_pct": info.weekly_utilization_pct,
            "weekly_resets_at": (
                weekly_resets_at.isoformat() if weekly_resets_at else None
            ),
            # Plan metadata (nullable)
            "subscription_type": info.subscription_type,
            "rate_limit_tier": info.rate_limit_tier,
            # Extra usage (nullable)
            "extra_usage_enabled": info.extra_usage_enabled,
            "extra_usage_monthly_limit": info.extra_usage_monthly_limit,
            "extra_usage_used": info.extra_usage_used,
            "extra_usage_utilization": info.extra_usage_utilization,
        }
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(json.dumps(data))
    except Exception as e:
        logger.debug("Failed to save snapshot: %s", e)


def _load_snapshot() -> LimitInfo | None:
    """Load last successful usage from disk. Returns None on any error."""
    try:
        data = json.loads(SNAPSHOT_PATH.read_text())
        resets_at, reset_reason = _parse_resets_at(data.get("resets_at"), "snapshot")
        if reset_reason in ("too_future", "parse_error"):
            _heal_snapshot_resets_at(data, reset_reason)
        last_sync = None
        if data.get("last_sync"):
            last_sync = datetime.datetime.fromisoformat(data["last_sync"])
        # Discard snapshot if its 5-hour window has already reset
        if reset_reason == "too_past":
            logger.debug("Snapshot expired (resets_at in past), discarding")
            return None
        # Weekly resets_at (nullable, lenient — ignore if invalid)
        weekly_resets_at = None
        raw_weekly_resets = data.get("weekly_resets_at")
        if raw_weekly_resets:
            weekly_resets_at, _ = _parse_resets_at(
                raw_weekly_resets, "snapshot weekly",
                max_future_sec=_WEEKLY_RESET_MAX_FUTURE_SEC,
            )
        return LimitInfo(
            source=data.get("source", "official"),
            utilization_pct=data.get("utilization_pct"),
            resets_at=resets_at,
            last_sync=last_sync,
            state=ProviderState.HEALTHY,
            confidence=Confidence.HIGH,
            weekly_utilization_pct=data.get("weekly_utilization_pct"),
            weekly_resets_at=weekly_resets_at,
            subscription_type=data.get("subscription_type"),
            rate_limit_tier=data.get("rate_limit_tier"),
            extra_usage_enabled=data.get("extra_usage_enabled"),
            extra_usage_monthly_limit=data.get("extra_usage_monthly_limit"),
            extra_usage_used=data.get("extra_usage_used"),
            extra_usage_utilization=data.get("extra_usage_utilization"),
        )
    except Exception as e:
        logger.debug("Failed to load snapshot: %s", e)
        return None


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------
class LimitProvider(ABC):
    """Interface for account limit data sources."""

    @abstractmethod
    def get_limit_info(self) -> LimitInfo:
        """Return current limit information."""
        ...

    @abstractmethod
    def get_state(self) -> ProviderState:
        """Return provider health state."""
        ...


# ---------------------------------------------------------------------------
# Official provider (OAuth API — same source as claude.ai)
# ---------------------------------------------------------------------------
class OfficialLimitProvider(LimitProvider):
    """Fetches real session usage from the Claude OAuth API.

    Uses the same data source as the claude.ai "Plan usage limits" page.
    Token is read from macOS Keychain (set by Claude Code on login).

    Polls every 60 seconds. On failures, returns last known data when
    available and applies a short local cooldown/backoff to avoid repeated
    failing requests and noisy logs.
    """

    CACHE_TTL_SEC = 55  # Just under 60s poll interval
    TOKEN_EXPIRED_COOLDOWN_SEC = 300
    RATE_LIMIT_BACKOFF_STEPS_SEC = (120, 300, 600)

    def __init__(self) -> None:
        self._cached: LimitInfo | None = None
        self._cache_time: datetime.datetime | None = None
        self._retry_after: datetime.datetime | None = None
        self._retry_reason: str | None = None
        self._rate_limit_step = 0
        # Keychain metadata (populated on each token read)
        self._subscription_type: str | None = None
        self._rate_limit_tier: str | None = None

    # ------------------------------------------------------------------
    # Token extraction and refresh
    # ------------------------------------------------------------------
    def _get_keychain_raw(self) -> tuple[str, dict | None]:
        """Read raw keychain entry. Returns (raw_str, parsed_dict_or_None)."""
        result = subprocess.run(
            ["security", "find-generic-password", "-s", _KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Keychain lookup failed (exit {result.returncode}): {result.stderr.strip()}"
            )
        raw = result.stdout.strip()
        try:
            return raw, json.loads(raw)
        except json.JSONDecodeError:
            return raw, None

    def _get_token(self) -> str:
        """Extract OAuth access token from macOS Keychain, refreshing proactively if near expiry."""
        raw, data = self._get_keychain_raw()
        try:
            if data is None:
                raise KeyError("not JSON")
            oauth = data["claudeAiOauth"]
            access_token = oauth["accessToken"]

            # Extract plan metadata from Keychain (available without extra API calls)
            self._subscription_type = oauth.get("subscriptionType")
            self._rate_limit_tier = oauth.get("rateLimitTier")

            # Proactive refresh: if token expires soon and we have a refresh token, refresh now
            expires_at_ms = oauth.get("expiresAt")
            refresh_token = oauth.get("refreshToken")
            if expires_at_ms and refresh_token:
                expires_in_sec = (expires_at_ms / 1000) - time.time()
                if expires_in_sec < _PROACTIVE_REFRESH_THRESHOLD_SEC:
                    logger.info(
                        "Token expires in %.0fs — proactively refreshing",
                        max(0.0, expires_in_sec),
                    )
                    try:
                        return self._refresh_oauth_token(refresh_token, data)
                    except Exception as e:
                        logger.warning("Proactive refresh failed (%s) — using existing token", e)

            return access_token
        except (KeyError, TypeError):
            # Might already be a raw token (future-proofing)
            if raw.startswith("sk-"):
                return raw
            raise RuntimeError(f"Unexpected Keychain credential format: {raw[:40]}...")

    def _refresh_oauth_token(self, refresh_token: str, keychain_data: dict) -> str:
        """Call the OAuth refresh endpoint, update the Keychain, and return the new access token."""
        body = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": _OAUTH_CLIENT_ID,
        }).encode()

        req = urllib.request.Request(
            _TOKEN_REFRESH_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Token refresh HTTP {e.code}: {e.reason}")

        new_access = resp_data.get("access_token")
        if not new_access:
            raise RuntimeError(f"Token refresh response missing access_token: {resp_data}")

        # Write updated tokens back to Keychain, preserving all existing fields
        updated_oauth = {**keychain_data.get("claudeAiOauth", {})}
        updated_oauth["accessToken"] = new_access
        if "refresh_token" in resp_data:
            updated_oauth["refreshToken"] = resp_data["refresh_token"]
        if "expires_in" in resp_data:
            updated_oauth["expiresAt"] = int((time.time() + resp_data["expires_in"]) * 1000)
        updated = {**keychain_data, "claudeAiOauth": updated_oauth}

        write = subprocess.run(
            [
                "security", "add-generic-password",
                "-U",  # update if exists
                "-s", _KEYCHAIN_SERVICE,
                "-a", getpass.getuser(),
                "-w", json.dumps(updated),
            ],
            capture_output=True, text=True, timeout=10,
        )
        if write.returncode != 0:
            logger.warning("Keychain write failed (%d): %s", write.returncode, write.stderr.strip())
        else:
            logger.info("Keychain updated with refreshed OAuth tokens")

        return new_access

    def _try_silent_refresh(self) -> str | None:
        """Try to silently refresh the OAuth token. Returns new access token or None on failure."""
        try:
            _, data = self._get_keychain_raw()
            if data is None:
                return None
            refresh_token = data.get("claudeAiOauth", {}).get("refreshToken")
            if not refresh_token:
                return None
            return self._refresh_oauth_token(refresh_token, data)
        except Exception as e:
            logger.warning("Silent token refresh failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # API call
    # ------------------------------------------------------------------
    def _fetch_usage(self, token: str) -> dict:
        """Call the OAuth usage endpoint and return the JSON response."""
        req = urllib.request.Request(
            _OAUTH_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-beta": _OAUTH_BETA,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise _RateLimitError()
            if e.code == 401:
                try:
                    body = json.loads(e.read().decode())
                    err_msg = body.get("error", {}).get("message", "Unauthorized")
                except Exception:
                    err_msg = "Unauthorized"
                raise _TokenExpiredError(err_msg)
            raise RuntimeError(f"API error {e.code}: {e.reason}")

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------
    def _cache_valid(self) -> bool:
        if self._cached is None or self._cache_time is None:
            return False
        age = (_now() - self._cache_time).total_seconds()
        return age < self.CACHE_TTL_SEC

    def _retry_guard_active(self) -> bool:
        if self._retry_after is None:
            return False
        if self._retry_after <= _now():
            self._retry_after = None
            self._retry_reason = None
            return False
        return True

    def _set_retry_guard(self, seconds: int, reason: str) -> None:
        self._retry_after = _now() + datetime.timedelta(seconds=seconds)
        self._retry_reason = reason

    def _clear_retry_guard(self) -> None:
        self._retry_after = None
        self._retry_reason = None
        self._rate_limit_step = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
    def get_state(self) -> ProviderState:
        if self._cached is not None:
            return ProviderState.HEALTHY
        return ProviderState.OFFLINE

    def try_snapshot_startup(self) -> bool:
        """Try to seed cache from disk snapshot on startup.

        Returns True if a fresh snapshot was loaded (saved <10 min ago,
        resets_at still in future). This avoids an API call on startup.
        """
        try:
            data = json.loads(SNAPSHOT_PATH.read_text())
            saved_at_str = data.get("saved_at")
            resets_at, reset_reason = _parse_resets_at(data.get("resets_at"), "startup snapshot")
            if not saved_at_str or resets_at is None:
                if reset_reason in ("too_future", "parse_error"):
                    _heal_snapshot_resets_at(data, reset_reason)
                return False

            saved_at = datetime.datetime.fromisoformat(saved_at_str)
            now = _now()

            # Snapshot must be recent (<10 min) and not expired
            age_minutes = (now - saved_at).total_seconds() / 60
            if age_minutes > 10 or reset_reason == "too_past":
                logger.debug("Snapshot too old (%.1f min) or expired, skipping", age_minutes)
                return False

            last_sync = None
            if data.get("last_sync"):
                last_sync = datetime.datetime.fromisoformat(data["last_sync"])

            # Weekly resets_at (nullable, lenient)
            weekly_resets_at = None
            raw_weekly_resets = data.get("weekly_resets_at")
            if raw_weekly_resets:
                weekly_resets_at, _ = _parse_resets_at(
                    raw_weekly_resets, "startup weekly",
                    max_future_sec=_WEEKLY_RESET_MAX_FUTURE_SEC,
                )

            info = LimitInfo(
                source=data.get("source", "official"),
                utilization_pct=data.get("utilization_pct"),
                resets_at=resets_at,
                last_sync=last_sync,
                state=ProviderState.HEALTHY,
                confidence=Confidence.HIGH,
                weekly_utilization_pct=data.get("weekly_utilization_pct"),
                weekly_resets_at=weekly_resets_at,
                subscription_type=data.get("subscription_type"),
                rate_limit_tier=data.get("rate_limit_tier"),
                extra_usage_enabled=data.get("extra_usage_enabled"),
                extra_usage_monthly_limit=data.get("extra_usage_monthly_limit"),
                extra_usage_used=data.get("extra_usage_used"),
                extra_usage_utilization=data.get("extra_usage_utilization"),
            )
            self._cached = info
            self._cache_time = now
            logger.info("Startup: loaded snapshot (%.1f%% used, saved %.0f min ago)",
                        info.utilization_pct or 0, age_minutes)
            return True
        except Exception as e:
            logger.debug("Snapshot startup failed: %s", e)
            return False

    def force_refresh(self) -> LimitInfo:
        """Clear cache and re-fetch."""
        self._cache_time = None
        self._cached = None
        self._retry_after = None
        self._retry_reason = None
        logger.info("Force refresh: cleared cache")
        return self.get_limit_info()

    def _parse_usage_data(self, data: dict) -> LimitInfo:
        """Parse an OAuth API usage response into a LimitInfo."""
        five_hour = data.get("five_hour", {})
        utilization = five_hour.get("utilization")  # fraction or percent

        if utilization is None:
            raise RuntimeError(f"Unexpected API response shape: {list(data.keys())}")

        resets_at, _ = _parse_resets_at(five_hour.get("resets_at"), "oauth api")

        # Weekly limit (None for student/edu accounts that have no weekly cap)
        seven_day = data.get("seven_day")
        weekly_utilization_pct = None
        weekly_resets_at = None
        if seven_day is not None:
            raw_weekly_util = seven_day.get("utilization")
            if raw_weekly_util is not None:
                weekly_utilization_pct = _normalize_utilization(raw_weekly_util)
            weekly_resets_at, _ = _parse_resets_at(
                seven_day.get("resets_at"), "oauth api weekly",
                max_future_sec=_WEEKLY_RESET_MAX_FUTURE_SEC,
            )

        weekly_cap_note = (
            "No weekly limit (student/edu account)"
            if seven_day is None
            else "Weekly cap may apply — check claude.ai for details"
        )

        # Extra usage / API credits
        extra = data.get("extra_usage") or {}
        extra_enabled = extra.get("is_enabled")
        extra_monthly_limit = extra.get("monthly_limit")
        extra_used = extra.get("used_credits")
        raw_extra_util = extra.get("utilization")
        extra_utilization = (
            _normalize_utilization(raw_extra_util) if raw_extra_util is not None else None
        )

        return LimitInfo(
            source="official (claude.ai)",
            plan_tier="unknown",
            daily_budget_usd=0.0,
            confidence=Confidence.HIGH,
            state=ProviderState.HEALTHY,
            last_sync=_now(),
            utilization_pct=_normalize_utilization(utilization),
            resets_at=resets_at,
            weekly_cap_note=weekly_cap_note,
            error=None,
            weekly_utilization_pct=weekly_utilization_pct,
            weekly_resets_at=weekly_resets_at,
            subscription_type=self._subscription_type,
            rate_limit_tier=self._rate_limit_tier,
            extra_usage_enabled=extra_enabled,
            extra_usage_monthly_limit=extra_monthly_limit,
            extra_usage_used=extra_used,
            extra_usage_utilization=extra_utilization,
        )

    def _store_usage(self, info: LimitInfo) -> None:
        """Cache a successful LimitInfo result and persist it to disk."""
        self._cached = info
        self._cache_time = _now()
        self._clear_retry_guard()
        _save_snapshot(info)
        logger.info("OAuth usage fetched: %.1f%% used", info.utilization_pct)

    def get_limit_info(self) -> LimitInfo:
        # Return cached data if still fresh
        if self._cache_valid() and self._cached is not None:
            return self._cached

        if self._retry_guard_active():
            retry_remaining = int((self._retry_after - _now()).total_seconds())
            logger.debug(
                "Retry guard active (%ds remaining) — using last known data",
                max(0, retry_remaining),
            )
            return self._fallback(self._retry_reason or "Temporarily unavailable")

        try:
            token = self._get_token()
            data = self._fetch_usage(token)
            info = self._parse_usage_data(data)
            self._store_usage(info)
            return info

        except _RateLimitError:
            backoff_sec = self.RATE_LIMIT_BACKOFF_STEPS_SEC[
                min(self._rate_limit_step, len(self.RATE_LIMIT_BACKOFF_STEPS_SEC) - 1)
            ]
            self._rate_limit_step = min(
                self._rate_limit_step + 1,
                len(self.RATE_LIMIT_BACKOFF_STEPS_SEC) - 1,
            )
            logger.info("429 rate limited — backing off for %ds", backoff_sec)
            self._set_retry_guard(backoff_sec, "Rate limited")
            return self._fallback("Rate limited")

        except _TokenExpiredError as e:
            logger.info("OAuth token expired: %s", e)
            self._rate_limit_step = 0
            # Try silent refresh before entering the cooldown period
            new_token = self._try_silent_refresh()
            if new_token:
                logger.info("Token refreshed silently after 401 — retrying fetch")
                try:
                    data = self._fetch_usage(new_token)
                    info = self._parse_usage_data(data)
                    self._store_usage(info)
                    return info
                except Exception as retry_err:
                    logger.warning("Retry after silent refresh failed: %s", retry_err)
            # Refresh unavailable or failed — enter normal cooldown
            self._set_retry_guard(
                self.TOKEN_EXPIRED_COOLDOWN_SEC,
                "Token expired — run: claude auth login",
            )
            return self._fallback("Token expired — run: claude auth login")

        except Exception as e:
            logger.warning("OfficialLimitProvider failed: %s", e)
            return self._fallback(str(e))

    def _fallback(self, reason: str) -> LimitInfo:
        """Return last known data as HEALTHY. No stale markers."""
        # Discard cache if its 5-hour window has already reset
        if self._cached is not None and self._cached.resets_at and self._cached.resets_at < _now():
            logger.debug("Cached data expired (resets_at in past), discarding")
            self._cached = None
            self._cache_time = None
        # Return last cached value as HEALTHY
        if self._cached is not None:
            return LimitInfo(
                source=self._cached.source,
                plan_tier=self._cached.plan_tier,
                daily_budget_usd=self._cached.daily_budget_usd,
                confidence=Confidence.HIGH,
                state=ProviderState.HEALTHY,
                last_sync=self._cached.last_sync,
                utilization_pct=self._cached.utilization_pct,
                resets_at=self._cached.resets_at,
                weekly_cap_note=self._cached.weekly_cap_note,
                error=reason,
                weekly_utilization_pct=self._cached.weekly_utilization_pct,
                weekly_resets_at=self._cached.weekly_resets_at,
                subscription_type=self._cached.subscription_type,
                rate_limit_tier=self._cached.rate_limit_tier,
                extra_usage_enabled=self._cached.extra_usage_enabled,
                extra_usage_monthly_limit=self._cached.extra_usage_monthly_limit,
                extra_usage_used=self._cached.extra_usage_used,
                extra_usage_utilization=self._cached.extra_usage_utilization,
            )
        # Try disk snapshot
        snapshot = _load_snapshot()
        if snapshot is not None:
            snapshot.error = reason
            return snapshot
        return LimitInfo(
            source="official (unavailable)",
            state=ProviderState.OFFLINE,
            error=reason,
        )


class _RateLimitError(Exception):
    """Sentinel for HTTP 429 responses."""


class _TokenExpiredError(Exception):
    """Sentinel for HTTP 401 token-expired responses."""


# ---------------------------------------------------------------------------
# Estimator (fallback when official provider unavailable)
# ---------------------------------------------------------------------------
class EstimatorLimitProvider(LimitProvider):
    """Estimates account limits from user-configured plan tier.

    All values are approximate and clearly labeled as estimates.
    If user sets daily_budget_usd in config, that takes precedence.
    """

    def __init__(self, config: dict) -> None:
        self._config = config
        self._state = ProviderState.HEALTHY
        self._last_sync = _now()

    def update_config(self, config: dict) -> None:
        """Update with fresh config (e.g., after settings change)."""
        self._config = config
        self._last_sync = _now()

    def get_state(self) -> ProviderState:
        plan_tier = self._config.get("plan_tier", "unknown")
        manual_budget = self._config.get("daily_budget_usd")
        if manual_budget is not None:
            return ProviderState.HEALTHY
        if plan_tier in PLAN_ESTIMATES:
            return ProviderState.HEALTHY
        return ProviderState.OFFLINE

    def get_limit_info(self, five_hour_window: WindowInfo | None = None) -> LimitInfo:
        plan_tier = self._config.get("plan_tier", "unknown")
        manual_budget = self._config.get("daily_budget_usd")

        if manual_budget is not None:
            budget = float(manual_budget)
            confidence = Confidence.MEDIUM
            source = "estimated (manual budget)"
        elif plan_tier in PLAN_ESTIMATES:
            est = PLAN_ESTIMATES[plan_tier]
            budget = est["daily_budget_usd"]
            confidence = est["confidence"]
            source = f"estimated ({plan_tier.replace('_', ' ').title()} plan)"
        else:
            budget = 100.0
            confidence = Confidence.LOW
            source = "estimated (unknown plan — using $100 default)"
            logger.warning("Unknown plan tier '%s', defaulting to $100 budget", plan_tier)

        return LimitInfo(
            source=source,
            plan_tier=plan_tier,
            daily_budget_usd=budget,
            confidence=confidence,
            state=self.get_state(),
            last_sync=self._last_sync,
            five_hour_window=five_hour_window,
            weekly_cap_note="Weekly cap may apply (not tracked locally)",
            error=None,
            utilization_pct=None,   # Cannot estimate without official data
            resets_at=None,
        )


# ---------------------------------------------------------------------------
# Composite provider — tries official first, falls back to estimator
# ---------------------------------------------------------------------------
class CompositeLimitProvider(LimitProvider):
    """Orchestrates OfficialLimitProvider (primary) and EstimatorLimitProvider (fallback)."""

    def __init__(self, config: dict) -> None:
        self._official = OfficialLimitProvider()
        self._estimator = EstimatorLimitProvider(config)

    def update_config(self, config: dict) -> None:
        self._estimator.update_config(config)

    def try_snapshot_startup(self) -> bool:
        """Try to seed official provider cache from disk snapshot."""
        return self._official.try_snapshot_startup()

    def force_refresh(self) -> LimitInfo:
        """Clear cache on the official provider and re-fetch."""
        return self._official.force_refresh()

    def get_state(self) -> ProviderState:
        official_state = self._official.get_state()
        if official_state == ProviderState.HEALTHY:
            return official_state
        return self._estimator.get_state()

    def get_limit_info(self) -> LimitInfo:
        official = self._official.get_limit_info()
        if official.state == ProviderState.HEALTHY and official.utilization_pct is not None:
            return official
        # Official unavailable — use estimator but carry through the
        # official error so the UI can show an actionable message.
        fallback = self._estimator.get_limit_info()
        if official.error:
            fallback.error = official.error
            fallback.state = official.state
        return fallback
