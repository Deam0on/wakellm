"""
Shared fixtures used across all test modules.
All fixtures are pure in-memory — no file I/O, no network, no subprocesses.
"""
import pytest


@pytest.fixture
def minimal_config():
    """Minimal valid config dict; mirrors what load_config() returns from YAML."""
    return {
        "runpod": {
            "api_key": "testapikey123",
            "pod_id":  "abc123def456",
        },
        "ssh": {
            "key_path": "/home/user/.ssh/id_ed25519",
        },
        "ports": [
            "11434:11434",
            "8080:8080",
        ],
        "startup": {
            "pod_start_timeout_minutes": 1,
            "ssh_boot_wait_seconds": 0,
        },
        "autokill": {
            "idle_timeout_minutes": 15,
            "hard_timeout_minutes": 120,
            "ollama_poll_interval_seconds": 30,
            "ollama_remote_port": 11434,
        },
        "api": {
            "enabled": True,
            "host": "127.0.0.1",
            "port": 8765,
        },
    }


@pytest.fixture
def mock_pod_info():
    """Realistic RunPod get_pod_info() response for a running pod."""
    return {
        "id": "abc123def456",
        "desiredStatus": "RUNNING",
        "runtime": {
            "ports": [
                {
                    "ip": "192.0.2.10",
                    "isIpPublic": True,
                    "privatePort": 22,
                    "publicPort": 43210,
                    "type": "tcp",
                },
                {
                    "ip": "192.0.2.10",
                    "isIpPublic": True,
                    "privatePort": 11434,
                    "publicPort": 11434,
                    "type": "http",
                },
            ]
        },
    }
