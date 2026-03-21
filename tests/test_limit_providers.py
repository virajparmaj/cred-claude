"""Tests for limit providers."""

from __future__ import annotations

import datetime
import json
from unittest.mock import MagicMock, patch

import pytest

from credclaude.limit_providers import (
    PLAN_ESTIMATES,
    CompositeLimitProvider,
    EstimatorLimitProvider,
    OfficialLimitProvider,
    _RateLimitError,
    _load_snapshot,
    _normalize_utilization,
    _save_snapshot,
)
from credclaude.models import Confidence, LimitInfo, ProviderState


# ---------------------------------------------------------------------------
# EstimatorLimitProvider
# ---------------------------------------------------------------------------
class TestEstimatorLimitProvider:
    def test_pro_plan(self):
        provider = EstimatorLimitProvider({"plan_tier": "pro"})
        info = provider.get_limit_info()
        assert info.plan_tier == "pro"
        assert info.daily_budget_usd == pytest.approx(15.0)
        assert info.confidence == Confidence.LOW
        assert info.source == "estimated (Pro plan)"
        assert info.state == ProviderState.HEALTHY

    def test_max_5x_plan(self):
        provider = EstimatorLimitProvider({"plan_tier": "max_5x"})
        info = provider.get_limit_info()
        assert info.daily_budget_usd == pytest.approx(75.0)
        assert "Max 5X" in info.source or "Max 5x" in info.source

    def test_max_20x_plan(self):
        provider = EstimatorLimitProvider({"plan_tier": "max_20x"})
        info = provider.get_limit_info()
        assert info.daily_budget_usd == pytest.approx(150.0)

    def test_unknown_tier_falls_back(self):
        provider = EstimatorLimitProvider({"plan_tier": "enterprise"})
        info = provider.get_limit_info()
        assert info.daily_budget_usd == pytest.approx(100.0)
        assert info.confidence == Confidence.LOW
        assert provider.get_state() == ProviderState.OFFLINE

    def test_manual_budget_override(self):
        provider = EstimatorLimitProvider({
            "plan_tier": "pro",
            "daily_budget_usd": 50.0,
        })
        info = provider.get_limit_info()
        assert info.daily_budget_usd == pytest.approx(50.0)
        assert info.confidence == Confidence.MEDIUM
        assert "manual" in info.source.lower()

    def test_manual_budget_none_uses_plan(self):
        provider = EstimatorLimitProvider({
            "plan_tier": "max_5x",
            "daily_budget_usd": None,
        })
        info = provider.get_limit_info()
        assert info.daily_budget_usd == pytest.approx(75.0)

    def test_weekly_cap_note_present(self):
        provider = EstimatorLimitProvider({"plan_tier": "pro"})
        info = provider.get_limit_info()
        assert "weekly" in info.weekly_cap_note.lower()

    def test_state_healthy_for_known_tier(self):
        provider = EstimatorLimitProvider({"plan_tier": "pro"})
        assert provider.get_state() == ProviderState.HEALTHY

    def test_state_offline_for_unknown_tier(self):
        provider = EstimatorLimitProvider({"plan_tier": "garbage"})
        assert provider.get_state() == ProviderState.OFFLINE

    def test_update_config(self):
        provider = EstimatorLimitProvider({"plan_tier": "pro"})
        assert provider.get_limit_info().daily_budget_usd == pytest.approx(15.0)
        provider.update_config({"plan_tier": "max_20x"})
        assert provider.get_limit_info().daily_budget_usd == pytest.approx(150.0)

    def test_all_plan_tiers_have_estimates(self):
        for tier in ("pro", "max_5x", "max_20x"):
            assert tier in PLAN_ESTIMATES
            assert PLAN_ESTIMATES[tier]["daily_budget_usd"] > 0

    def test_utilization_pct_is_none(self):
        """Estimator never returns a real utilization_pct."""
        provider = EstimatorLimitProvider({"plan_tier": "pro"})
        info = provider.get_limit_info()
        assert info.utilization_pct is None

    def test_resets_at_is_none(self):
        """Estimator never returns resets_at."""
        provider = EstimatorLimitProvider({"plan_tier": "pro"})
        info = provider.get_limit_info()
        assert info.resets_at is None


# ---------------------------------------------------------------------------
# OfficialLimitProvider
# ---------------------------------------------------------------------------
def _make_api_response(utilization: float = 0.84, resets_in_hours: float = 1.5) -> bytes:
    """Build a fake OAuth API JSON response."""
    resets_at = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(hours=resets_in_hours)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    return json.dumps({
        "five_hour": {
            "utilization": utilization,
            "resets_at": resets_at,
        }
    }).encode()


def _make_keychain_output(token: str = "sk-ant-oat01-testtoken") -> str:
    """Build a fake Keychain JSON blob as returned by security."""
    return json.dumps({"claudeAiOauth": {"accessToken": token}})


class TestOfficialLimitProvider:
    def _mock_subprocess(self, token: str = "sk-ant-oat01-testtoken"):
        """Return a mock for subprocess.run that returns a keychain credential."""
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = _make_keychain_output(token)
        return mock

    def _mock_urlopen(self, body: bytes):
        """Return a mock for urllib.request.urlopen."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_successful_fetch(self):
        provider = OfficialLimitProvider()
        body = _make_api_response(utilization=0.84, resets_in_hours=1.5)

        with patch("subprocess.run", return_value=self._mock_subprocess()):
            with patch("urllib.request.urlopen", return_value=self._mock_urlopen(body)):
                info = provider.get_limit_info()

        assert info.utilization_pct == pytest.approx(84.0)
        assert info.confidence == Confidence.HIGH
        assert info.state == ProviderState.HEALTHY
        assert info.source == "official (claude.ai)"
        assert info.resets_at is not None

    def test_token_parsing_json_wrapper(self):
        """Parses {"claudeAiOauth": {"accessToken": "..."}} from Keychain."""
        provider = OfficialLimitProvider()
        body = _make_api_response()

        captured_headers = {}

        def fake_urlopen(req, timeout=None):
            captured_headers.update(req.headers)
            return self._mock_urlopen(body)

        with patch("subprocess.run", return_value=self._mock_subprocess("sk-ant-oat01-realtoken")):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                provider.get_limit_info()

        # Verify the correct token was used (not the raw JSON blob)
        assert "Authorization" in captured_headers
        assert "sk-ant-oat01-realtoken" in captured_headers["Authorization"]

    def test_raw_token_fallback(self):
        """If Keychain returns a raw sk- token (no JSON wrapper), uses it directly."""
        provider = OfficialLimitProvider()
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "sk-ant-oat01-rawtoken"
        body = _make_api_response()

        with patch("subprocess.run", return_value=mock_proc):
            with patch("urllib.request.urlopen", return_value=self._mock_urlopen(body)):
                info = provider.get_limit_info()

        assert info.utilization_pct is not None

    def test_caches_response(self):
        """Second call within TTL uses cache, no extra subprocess/HTTP call."""
        provider = OfficialLimitProvider()
        body = _make_api_response()

        with patch("subprocess.run", return_value=self._mock_subprocess()) as mock_proc:
            with patch("urllib.request.urlopen", return_value=self._mock_urlopen(body)) as mock_url:
                provider.get_limit_info()
                provider.get_limit_info()  # Should use cache

        # subprocess and urlopen each called only once
        assert mock_proc.call_count == 1
        assert mock_url.call_count == 1

    def test_keychain_failure_returns_offline(self):
        """Keychain lookup failure with no cache → OFFLINE state."""
        provider = OfficialLimitProvider()
        mock_proc = MagicMock()
        mock_proc.returncode = 44  # not found
        mock_proc.stderr = "SecKeychainSearchCopyNext"

        with patch("subprocess.run", return_value=mock_proc):
            with patch("credclaude.limit_providers._load_snapshot", return_value=None):
                info = provider.get_limit_info()

        assert info.state == ProviderState.OFFLINE
        assert info.error is not None

    def test_429_returns_cached_as_healthy(self):
        """HTTP 429 → returns cached data as HEALTHY (no backoff)."""
        import urllib.error
        provider = OfficialLimitProvider()
        body = _make_api_response(utilization=0.5)

        # First: successful fetch
        with patch("subprocess.run", return_value=self._mock_subprocess()):
            with patch("urllib.request.urlopen", return_value=self._mock_urlopen(body)):
                provider.get_limit_info()

        # Expire cache
        provider._cache_time = datetime.datetime.now().astimezone() - datetime.timedelta(seconds=120)

        # Now: 429
        def raise_429(*args, **kwargs):
            raise urllib.error.HTTPError(
                url=_OAUTH_URL, code=429, msg="Rate Limited",
                hdrs=None, fp=None,
            )

        with patch("subprocess.run", return_value=self._mock_subprocess()):
            with patch("urllib.request.urlopen", side_effect=raise_429):
                info = provider.get_limit_info()

        assert info.utilization_pct == pytest.approx(50.0)
        assert info.state == ProviderState.HEALTHY  # No stale/degraded

    def test_successful_fetch_after_failure(self):
        """After a failure, next successful fetch works normally."""
        provider = OfficialLimitProvider()

        # First: failure
        mock_proc = MagicMock()
        mock_proc.returncode = 44
        mock_proc.stderr = "not found"

        with patch("subprocess.run", return_value=mock_proc):
            with patch("credclaude.limit_providers._load_snapshot", return_value=None):
                provider.get_limit_info()

        # Now: success
        body = _make_api_response(utilization=0.70)
        with patch("subprocess.run", return_value=self._mock_subprocess()):
            with patch("urllib.request.urlopen", return_value=self._mock_urlopen(body)):
                info = provider.get_limit_info()

        assert info.utilization_pct == pytest.approx(70.0)
        assert info.state == ProviderState.HEALTHY

    def test_stale_cache_returned_on_failure(self):
        """When API fails, returns cached data as HEALTHY."""
        provider = OfficialLimitProvider()
        body = _make_api_response(utilization=0.5)

        # First: successful fetch (populates cache)
        with patch("subprocess.run", return_value=self._mock_subprocess()):
            with patch("urllib.request.urlopen", return_value=self._mock_urlopen(body)):
                provider.get_limit_info()

        # Expire cache
        provider._cache_time = datetime.datetime.now().astimezone() - datetime.timedelta(seconds=120)

        # Now: keychain failure
        mock_proc = MagicMock()
        mock_proc.returncode = 44
        mock_proc.stderr = "not found"

        with patch("subprocess.run", return_value=mock_proc):
            info = provider.get_limit_info()

        # Should return cached data as HEALTHY
        assert info.utilization_pct == pytest.approx(50.0)
        assert info.state == ProviderState.HEALTHY


# ---------------------------------------------------------------------------
# CompositeLimitProvider
# ---------------------------------------------------------------------------
class TestCompositeLimitProvider:
    def test_uses_official_when_available(self):
        provider = CompositeLimitProvider({"plan_tier": "pro"})
        body = _make_api_response(utilization=0.75)

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = _make_keychain_output()

        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("subprocess.run", return_value=mock_proc):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                info = provider.get_limit_info()

        assert info.confidence == Confidence.HIGH
        assert info.utilization_pct == pytest.approx(75.0)
        assert "official" in info.source

    def test_falls_back_to_estimator_when_official_fails(self):
        """With no cache and no disk snapshot, falls back to estimator."""
        provider = CompositeLimitProvider({"plan_tier": "pro"})

        mock_proc = MagicMock()
        mock_proc.returncode = 44
        mock_proc.stderr = "not found"

        with patch("subprocess.run", return_value=mock_proc):
            with patch("credclaude.limit_providers._load_snapshot", return_value=None):
                info = provider.get_limit_info()

        assert "estimated" in info.source
        assert info.utilization_pct is None  # Estimator can't provide real %

    def test_falls_back_to_snapshot_when_official_fails(self):
        """With no cache but a disk snapshot, returns snapshot data as HEALTHY."""
        provider = CompositeLimitProvider({"plan_tier": "pro"})

        mock_proc = MagicMock()
        mock_proc.returncode = 44
        mock_proc.stderr = "not found"

        snapshot = LimitInfo(
            source="official (claude.ai)",
            utilization_pct=42.0,
            state=ProviderState.HEALTHY,
            confidence=Confidence.HIGH,
        )

        with patch("subprocess.run", return_value=mock_proc):
            with patch("credclaude.limit_providers._load_snapshot", return_value=snapshot):
                info = provider.get_limit_info()

        assert info.utilization_pct == pytest.approx(42.0)
        assert info.state == ProviderState.HEALTHY

    def test_update_config_propagates(self):
        provider = CompositeLimitProvider({"plan_tier": "pro"})
        provider.update_config({"plan_tier": "max_20x"})
        # Estimator should reflect the new config on fallback (no snapshot)
        mock_proc = MagicMock()
        mock_proc.returncode = 44
        mock_proc.stderr = "not found"

        with patch("subprocess.run", return_value=mock_proc):
            with patch("credclaude.limit_providers._load_snapshot", return_value=None):
                info = provider.get_limit_info()

        assert info.daily_budget_usd == pytest.approx(150.0)

    def test_force_refresh_clears_cache(self):
        """force_refresh() clears cache and re-fetches."""
        provider = CompositeLimitProvider({"plan_tier": "pro"})

        body = _make_api_response(utilization=0.60)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = _make_keychain_output()

        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("subprocess.run", return_value=mock_proc):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                info = provider.force_refresh()

        assert info.utilization_pct == pytest.approx(60.0)
        assert info.state == ProviderState.HEALTHY

    def test_official_error_propagates_to_fallback(self):
        """When official fails (no snapshot), its error message appears in fallback result."""
        provider = CompositeLimitProvider({"plan_tier": "pro"})

        mock_proc = MagicMock()
        mock_proc.returncode = 44
        mock_proc.stderr = "not found"

        with patch("subprocess.run", return_value=mock_proc):
            with patch("credclaude.limit_providers._load_snapshot", return_value=None):
                info = provider.get_limit_info()

        assert info.error is not None
        assert "estimated" in info.source


# ---------------------------------------------------------------------------
# Token expired — actionable message
# ---------------------------------------------------------------------------
class TestTokenExpired:
    def test_error_mentions_auth_login(self, tmp_path):
        """401 error message should tell user to run 'claude auth login'."""
        import urllib.error
        provider = OfficialLimitProvider()

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = _make_keychain_output()

        def raise_401(*args, **kwargs):
            err = urllib.error.HTTPError(
                url=_OAUTH_URL, code=401, msg="Unauthorized",
                hdrs=None, fp=MagicMock(),
            )
            err.read = lambda: json.dumps({
                "error": {"message": "OAuth token has expired."}
            }).encode()
            raise err

        snapshot_path = tmp_path / "nonexistent.json"
        with patch("credclaude.limit_providers.SNAPSHOT_PATH", snapshot_path):
            with patch("subprocess.run", return_value=mock_proc):
                with patch("urllib.request.urlopen", side_effect=raise_401):
                    info = provider.get_limit_info()

        assert "claude auth login" in info.error

    def test_cached_data_shown_on_token_expiry(self, tmp_path):
        """During token expiry, cached data is shown as HEALTHY."""
        import urllib.error

        future = (datetime.datetime.now(datetime.timezone.utc)
                  + datetime.timedelta(hours=2))
        snapshot_path = tmp_path / "last_usage.json"
        snapshot_path.write_text(json.dumps({
            "utilization_pct": 55.0,
            "resets_at": future.isoformat(),
            "last_sync": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source": "official (claude.ai)",
        }))

        provider = OfficialLimitProvider()

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = _make_keychain_output()

        def raise_401(*args, **kwargs):
            err = urllib.error.HTTPError(
                url=_OAUTH_URL, code=401, msg="Unauthorized",
                hdrs=None, fp=MagicMock(),
            )
            err.read = lambda: json.dumps({
                "error": {"message": "OAuth token has expired."}
            }).encode()
            raise err

        with patch("credclaude.limit_providers.SNAPSHOT_PATH", snapshot_path):
            with patch("subprocess.run", return_value=mock_proc):
                with patch("urllib.request.urlopen", side_effect=raise_401):
                    info = provider.get_limit_info()

        assert info.utilization_pct == pytest.approx(55.0)
        assert info.state == ProviderState.HEALTHY
        assert "claude auth login" in info.error


# ---------------------------------------------------------------------------
# Utilization normalization
# ---------------------------------------------------------------------------
class TestNormalizeUtilization:
    def test_fraction_format(self):
        """0.64 (fraction) → 64.0%."""
        assert _normalize_utilization(0.64) == pytest.approx(64.0)

    def test_percent_format(self):
        """64.0 (already percent) → 64.0%."""
        assert _normalize_utilization(64.0) == pytest.approx(64.0)

    def test_clamped_above_100(self):
        """Values > 100 clamped to 100."""
        assert _normalize_utilization(150.0) == pytest.approx(100.0)

    def test_zero(self):
        """Zero stays zero."""
        assert _normalize_utilization(0.0) == pytest.approx(0.0)

    def test_one_treated_as_fraction(self):
        """1.0 is treated as 100% (fraction), not 1%."""
        assert _normalize_utilization(1.0) == pytest.approx(100.0)

    def test_api_response_fraction(self):
        """End-to-end: API returns 0.64 → provider shows 64%."""
        provider = OfficialLimitProvider()
        body = _make_api_response(utilization=0.64)

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = _make_keychain_output()

        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("subprocess.run", return_value=mock_proc):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                info = provider.get_limit_info()

        assert info.utilization_pct == pytest.approx(64.0)

    def test_api_response_percent(self):
        """End-to-end: API returns 64.0 → provider shows 64%."""
        provider = OfficialLimitProvider()
        body = _make_api_response(utilization=64.0)

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = _make_keychain_output()

        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("subprocess.run", return_value=mock_proc):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                info = provider.get_limit_info()

        assert info.utilization_pct == pytest.approx(64.0)


# ---------------------------------------------------------------------------
# Disk snapshot persistence
# ---------------------------------------------------------------------------
class TestDiskSnapshot:
    def _future_resets_at(self):
        """Return a resets_at 2 hours in the future (won't be discarded)."""
        return (datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(hours=2))

    def test_save_and_load(self, tmp_path):
        """Round-trip: save → load returns same data."""
        snapshot_path = tmp_path / "last_usage.json"
        future = self._future_resets_at()
        info = LimitInfo(
            source="official (claude.ai)",
            utilization_pct=64.0,
            resets_at=future,
            last_sync=datetime.datetime.now(datetime.timezone.utc),
        )
        with patch("credclaude.limit_providers.SNAPSHOT_PATH", snapshot_path):
            _save_snapshot(info)
            loaded = _load_snapshot()

        assert loaded is not None
        assert loaded.utilization_pct == pytest.approx(64.0)
        assert loaded.state == ProviderState.HEALTHY
        assert "official" in loaded.source

    def test_expired_snapshot_discarded(self, tmp_path):
        """Snapshot with resets_at in the past is discarded."""
        snapshot_path = tmp_path / "last_usage.json"
        past = (datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(hours=1))
        info = LimitInfo(
            source="official (claude.ai)",
            utilization_pct=64.0,
            resets_at=past,
            last_sync=datetime.datetime.now(datetime.timezone.utc),
        )
        with patch("credclaude.limit_providers.SNAPSHOT_PATH", snapshot_path):
            _save_snapshot(info)
            loaded = _load_snapshot()

        assert loaded is None

    def test_missing_file_returns_none(self, tmp_path):
        """No snapshot file → None."""
        snapshot_path = tmp_path / "nonexistent.json"
        with patch("credclaude.limit_providers.SNAPSHOT_PATH", snapshot_path):
            assert _load_snapshot() is None

    def test_fallback_on_failure(self, tmp_path):
        """Fresh provider with no cache falls back to disk snapshot as HEALTHY."""
        snapshot_path = tmp_path / "last_usage.json"
        future = self._future_resets_at()
        # Write a snapshot manually
        snapshot_path.write_text(json.dumps({
            "utilization_pct": 42.0,
            "resets_at": future.isoformat(),
            "last_sync": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source": "official (claude.ai)",
        }))

        provider = OfficialLimitProvider()
        mock_proc = MagicMock()
        mock_proc.returncode = 44
        mock_proc.stderr = "not found"

        with patch("credclaude.limit_providers.SNAPSHOT_PATH", snapshot_path):
            with patch("subprocess.run", return_value=mock_proc):
                info = provider.get_limit_info()

        assert info.utilization_pct == pytest.approx(42.0)
        assert "official" in info.source
        assert info.error is not None


# ---------------------------------------------------------------------------
# Snapshot startup
# ---------------------------------------------------------------------------
class TestSnapshotStartup:
    def _future_resets_at(self):
        return (datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(hours=2))

    def test_fresh_snapshot_seeds_cache(self, tmp_path):
        """Fresh snapshot (<10 min old) seeds the provider cache."""
        snapshot_path = tmp_path / "last_usage.json"
        future = self._future_resets_at()
        now = datetime.datetime.now(datetime.timezone.utc)
        snapshot_path.write_text(json.dumps({
            "utilization_pct": 64.0,
            "resets_at": future.isoformat(),
            "last_sync": now.isoformat(),
            "source": "official (claude.ai)",
            "saved_at": now.isoformat(),
        }))

        provider = OfficialLimitProvider()
        with patch("credclaude.limit_providers.SNAPSHOT_PATH", snapshot_path):
            result = provider.try_snapshot_startup()

        assert result is True
        assert provider._cached is not None
        assert provider._cached.utilization_pct == pytest.approx(64.0)
        assert provider._cached.state == ProviderState.HEALTHY

    def test_old_snapshot_rejected(self, tmp_path):
        """Snapshot older than 10 minutes is rejected."""
        snapshot_path = tmp_path / "last_usage.json"
        future = self._future_resets_at()
        old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=15)
        snapshot_path.write_text(json.dumps({
            "utilization_pct": 64.0,
            "resets_at": future.isoformat(),
            "last_sync": old.isoformat(),
            "source": "official (claude.ai)",
            "saved_at": old.isoformat(),
        }))

        provider = OfficialLimitProvider()
        with patch("credclaude.limit_providers.SNAPSHOT_PATH", snapshot_path):
            result = provider.try_snapshot_startup()

        assert result is False
        assert provider._cached is None

    def test_expired_snapshot_rejected(self, tmp_path):
        """Snapshot with resets_at in the past is rejected."""
        snapshot_path = tmp_path / "last_usage.json"
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        now = datetime.datetime.now(datetime.timezone.utc)
        snapshot_path.write_text(json.dumps({
            "utilization_pct": 64.0,
            "resets_at": past.isoformat(),
            "last_sync": now.isoformat(),
            "source": "official (claude.ai)",
            "saved_at": now.isoformat(),
        }))

        provider = OfficialLimitProvider()
        with patch("credclaude.limit_providers.SNAPSHOT_PATH", snapshot_path):
            result = provider.try_snapshot_startup()

        assert result is False

    def test_missing_snapshot_returns_false(self, tmp_path):
        """No snapshot file returns False."""
        snapshot_path = tmp_path / "nonexistent.json"
        provider = OfficialLimitProvider()
        with patch("credclaude.limit_providers.SNAPSHOT_PATH", snapshot_path):
            result = provider.try_snapshot_startup()

        assert result is False

    def test_snapshot_missing_saved_at_rejected(self, tmp_path):
        """Snapshot without saved_at field is rejected."""
        snapshot_path = tmp_path / "last_usage.json"
        future = self._future_resets_at()
        snapshot_path.write_text(json.dumps({
            "utilization_pct": 64.0,
            "resets_at": future.isoformat(),
            "source": "official (claude.ai)",
        }))

        provider = OfficialLimitProvider()
        with patch("credclaude.limit_providers.SNAPSHOT_PATH", snapshot_path):
            result = provider.try_snapshot_startup()

        assert result is False

    def test_composite_try_snapshot_startup(self, tmp_path):
        """CompositeLimitProvider delegates to official."""
        snapshot_path = tmp_path / "last_usage.json"
        future = self._future_resets_at()
        now = datetime.datetime.now(datetime.timezone.utc)
        snapshot_path.write_text(json.dumps({
            "utilization_pct": 72.0,
            "resets_at": future.isoformat(),
            "last_sync": now.isoformat(),
            "source": "official (claude.ai)",
            "saved_at": now.isoformat(),
        }))

        provider = CompositeLimitProvider({"plan_tier": "pro"})
        with patch("credclaude.limit_providers.SNAPSHOT_PATH", snapshot_path):
            result = provider.try_snapshot_startup()

        assert result is True


# Import needed in test scope
_OAUTH_URL = "https://api.anthropic.com/api/oauth/usage"
