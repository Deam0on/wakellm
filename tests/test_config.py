"""Tests for wakellm/config.py"""
import os
import sys
import stat

import pytest

from wakellm.config import (
    load_config,
    load_config_from_env,
    validate_config,
    validate_pod_id,
    cfg,
    ollama_local_port,
    _ENV_SSH_KEY_TMP,
)


# ---------------------------------------------------------------------------
# load_config — delegates to load_config_from_env
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def _base_env(self, monkeypatch):
        monkeypatch.setenv("WAKELLM_RUNPOD_API_KEY", "env-api-key")
        monkeypatch.setenv("WAKELLM_RUNPOD_POD_ID", "abc123def456")
        monkeypatch.setenv("WAKELLM_SSH_KEY_PATH", "/tmp/id_ed25519")
        monkeypatch.setenv("WAKELLM_PORTS", "11434:11434,8080:8080")

    def test_happy_path(self, monkeypatch):
        self._base_env(monkeypatch)
        result = load_config()
        assert result["runpod"]["api_key"] == "env-api-key"

    def test_missing_required_vars_exits(self, monkeypatch):
        for v in ("WAKELLM_RUNPOD_API_KEY", "WAKELLM_RUNPOD_POD_ID",
                  "WAKELLM_SSH_KEY_PATH", "WAKELLM_SSH_KEY", "WAKELLM_PORTS"):
            monkeypatch.delenv(v, raising=False)
        with pytest.raises(SystemExit) as exc:
            load_config()
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# load_config_from_env
# ---------------------------------------------------------------------------

class TestLoadConfigFromEnv:
    def _base_env(self, monkeypatch):
        monkeypatch.setenv("WAKELLM_RUNPOD_API_KEY", "env-api-key")
        monkeypatch.setenv("WAKELLM_RUNPOD_POD_ID", "abc123def456")
        monkeypatch.setenv("WAKELLM_SSH_KEY_PATH", "/tmp/id_ed25519")
        monkeypatch.setenv("WAKELLM_PORTS", "11434:11434,8080:8080")

    def test_happy_path(self, monkeypatch):
        self._base_env(monkeypatch)
        result = load_config_from_env()
        assert result["runpod"]["api_key"] == "env-api-key"
        assert result["runpod"]["pod_id"] == "abc123def456"
        assert result["ssh"]["key_path"] == "/tmp/id_ed25519"
        assert result["ports"] == ["11434:11434", "8080:8080"]

    def test_defaults_applied(self, monkeypatch):
        self._base_env(monkeypatch)
        result = load_config_from_env()
        assert result["startup"]["pod_start_timeout_minutes"] == 5
        assert result["startup"]["ssh_boot_wait_seconds"] == 10
        assert result["autokill"]["idle_timeout_minutes"] == 15
        assert result["autokill"]["hard_timeout_minutes"] == 120
        assert result["api"]["host"] == "127.0.0.1"
        assert result["api"]["port"] == 8765
        assert result["api"]["enabled"] is True

    def test_custom_overrides(self, monkeypatch):
        self._base_env(monkeypatch)
        monkeypatch.setenv("WAKELLM_STARTUP_TIMEOUT", "3")
        monkeypatch.setenv("WAKELLM_AUTOKILL_IDLE", "5")
        monkeypatch.setenv("WAKELLM_API_ENABLED", "false")
        result = load_config_from_env()
        assert result["startup"]["pod_start_timeout_minutes"] == 3
        assert result["autokill"]["idle_timeout_minutes"] == 5
        assert result["api"]["enabled"] is False

    def test_missing_required_vars_raises(self, monkeypatch):
        # Ensure none of the required vars are set
        for v in ("WAKELLM_RUNPOD_API_KEY", "WAKELLM_RUNPOD_POD_ID",
                  "WAKELLM_SSH_KEY_PATH", "WAKELLM_SSH_KEY", "WAKELLM_PORTS"):
            monkeypatch.delenv(v, raising=False)
        with pytest.raises(EnvironmentError):
            load_config_from_env()

    def test_ssh_key_content_written_to_tmp(self, monkeypatch, tmp_path):
        self._base_env(monkeypatch)
        monkeypatch.delenv("WAKELLM_SSH_KEY_PATH", raising=False)
        monkeypatch.setenv("WAKELLM_SSH_KEY", "-----BEGIN OPENSSH PRIVATE KEY-----\nfakekey\n-----END OPENSSH PRIVATE KEY-----")
        # Redirect the tmp path so we don't pollute /tmp in CI
        monkeypatch.setattr("wakellm.config._ENV_SSH_KEY_TMP", str(tmp_path / "wakellm_ssh_key"))
        result = load_config_from_env()
        written = tmp_path / "wakellm_ssh_key"
        assert written.exists()
        assert "fakekey" in written.read_text()
        # Must be 0600
        mode = stat.S_IMODE(written.stat().st_mode)
        assert mode == 0o600
        assert result["ssh"]["key_path"] == str(written)

    def test_ports_whitespace_stripped(self, monkeypatch):
        self._base_env(monkeypatch)
        monkeypatch.setenv("WAKELLM_PORTS", " 11434:11434 , 8080:8080 ")
        result = load_config_from_env()
        assert result["ports"] == ["11434:11434", "8080:8080"]


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------

class TestValidateConfig:
    def test_valid_config_passes(self, minimal_config):
        validate_config(minimal_config)  # should not raise or exit

    def test_missing_runpod_section_exits(self, minimal_config):
        del minimal_config["runpod"]
        with pytest.raises(SystemExit) as exc:
            validate_config(minimal_config)
        assert exc.value.code == 1

    def test_missing_ssh_section_exits(self, minimal_config):
        del minimal_config["ssh"]
        with pytest.raises(SystemExit):
            validate_config(minimal_config)

    def test_empty_api_key_exits(self, minimal_config):
        minimal_config["runpod"]["api_key"] = ""
        with pytest.raises(SystemExit):
            validate_config(minimal_config)

    def test_ports_not_a_list_exits(self, minimal_config):
        minimal_config["ports"] = "11434:11434"
        with pytest.raises(SystemExit):
            validate_config(minimal_config)

    def test_empty_ports_list_exits(self, minimal_config):
        minimal_config["ports"] = []
        with pytest.raises(SystemExit):
            validate_config(minimal_config)


# ---------------------------------------------------------------------------
# validate_pod_id
# ---------------------------------------------------------------------------

class TestValidatePodId:
    @pytest.mark.parametrize("pod_id", [
        "abc123de",           # 8 chars — minimum
        "abc123def456defabc0",  # 20 chars — maximum
        "abc-123-def",        # hyphens in middle
        "6068y77xfq1rux",     # real-world example
    ])
    def test_valid_ids(self, pod_id):
        validate_pod_id(pod_id)  # must not exit

    @pytest.mark.parametrize("pod_id", [
        "ABC123DE",            # uppercase
        "abc123d",             # 7 chars — too short
        "abc123def456defabc012",  # 21 chars — too long
        "abc_123_def",         # underscores not allowed
        "abc 123 def",         # spaces
        "-abc123def",          # leading hyphen
        "abc123def-",          # trailing hyphen
        "",                    # empty
    ])
    def test_invalid_ids_exit(self, pod_id):
        with pytest.raises(SystemExit):
            validate_pod_id(pod_id)


# ---------------------------------------------------------------------------
# cfg accessor
# ---------------------------------------------------------------------------

class TestCfgAccessor:
    def test_present_key(self, minimal_config):
        assert cfg(minimal_config, "api", "port", 9999) == 8765

    def test_missing_key_returns_default(self, minimal_config):
        assert cfg(minimal_config, "api", "nonexistent", 42) == 42

    def test_missing_section_returns_default(self, minimal_config):
        assert cfg(minimal_config, "nosection", "key", "fallback") == "fallback"


# ---------------------------------------------------------------------------
# ollama_local_port
# ---------------------------------------------------------------------------

class TestOllamaLocalPort:
    def test_standard_mapping(self, minimal_config):
        assert ollama_local_port(minimal_config) == 11434

    def test_custom_local_port(self, minimal_config):
        minimal_config["ports"] = ["19434:11434"]
        assert ollama_local_port(minimal_config) == 19434

    def test_no_matching_port(self, minimal_config):
        minimal_config["ports"] = ["8080:8080"]
        assert ollama_local_port(minimal_config) is None

    def test_custom_ollama_remote_port(self, minimal_config):
        minimal_config["ports"] = ["9999:9090"]
        minimal_config["autokill"]["ollama_remote_port"] = 9090
        assert ollama_local_port(minimal_config) == 9999
