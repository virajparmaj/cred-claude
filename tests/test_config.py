"""Tests for config loading and saving."""

from __future__ import annotations

import json

import pytest

from credclaude import config as config_mod
from credclaude.config import DEFAULT_CONFIG, load_config, save_config


@pytest.fixture
def config_env(tmp_path, monkeypatch):
    """Redirect config paths to tmp_path for isolation."""
    app_dir = tmp_path / ".credclaude"
    app_dir.mkdir()
    config_path = app_dir / "config.json"
    monkeypatch.setattr(config_mod, "APP_DIR", app_dir)
    monkeypatch.setattr(config_mod, "CONFIG_PATH", config_path)
    return config_path


class TestLoadConfig:
    def test_returns_defaults_when_no_file(self, config_env):
        cfg = load_config()
        assert cfg["billing_day"] == 1
        assert cfg["plan_tier"] == "pro"
        assert cfg["auto_reauth_enabled"] is True
        assert cfg["auto_reauth_cooldown_sec"] == 1800

    def test_reads_existing_config(self, config_env):
        config_env.write_text(json.dumps({"billing_day": 15, "plan_tier": "max_5x"}))
        cfg = load_config()
        assert cfg["billing_day"] == 15
        assert cfg["plan_tier"] == "max_5x"

    def test_backfills_missing_keys(self, config_env):
        config_env.write_text(json.dumps({"billing_day": 10}))
        cfg = load_config()
        assert cfg["billing_day"] == 10
        assert "warn_at_pct" in cfg
        assert "plan_tier" in cfg
        assert "auto_reauth_enabled" in cfg
        assert "auto_reauth_cooldown_sec" in cfg

    def test_migrates_daily_message_limit(self, config_env):
        config_env.write_text(json.dumps({
            "daily_message_limit": 200,
            "billing_day": 1,
        }))
        cfg = load_config()
        assert "daily_message_limit" not in cfg
        assert "daily_budget_usd" in cfg

    def test_corrupt_file_returns_defaults(self, config_env):
        config_env.write_text("not json!!!")
        cfg = load_config()
        assert cfg == DEFAULT_CONFIG

    def test_invalid_reauth_fields_reset_to_defaults(self, config_env):
        config_env.write_text(json.dumps({
            "auto_reauth_enabled": "yes",
            "auto_reauth_cooldown_sec": -1,
        }))
        cfg = load_config()
        assert cfg["auto_reauth_enabled"] is True
        assert cfg["auto_reauth_cooldown_sec"] == 1800


class TestSaveConfig:
    def test_round_trip(self, config_env):
        cfg = {"billing_day": 7, "plan_tier": "max_20x", "daily_budget_usd": 200.0}
        save_config(cfg)
        loaded = json.loads(config_env.read_text())
        assert loaded["billing_day"] == 7
        assert loaded["plan_tier"] == "max_20x"

    def test_creates_directory(self, tmp_path, monkeypatch):
        app_dir = tmp_path / "new_dir"
        config_path = app_dir / "config.json"
        monkeypatch.setattr(config_mod, "APP_DIR", app_dir)
        monkeypatch.setattr(config_mod, "CONFIG_PATH", config_path)
        save_config({"billing_day": 1})
        assert config_path.exists()
