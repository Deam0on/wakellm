"""Tests for wakellm/api.py — uses Flask test client, no real HTTP."""
import threading

import pytest

from wakellm.api import build_flask_app
from wakellm.orchestrator import WakeLLM


@pytest.fixture
def mock_engine(minimal_config, mocker):
    """A WakeLLM instance with all external I/O mocked away."""
    mocker.patch("wakellm.orchestrator.load_config", return_value=minimal_config)
    mocker.patch("wakellm.orchestrator.validate_config")
    mocker.patch("wakellm.orchestrator.validate_pod_id")
    mocker.patch("wakellm.orchestrator.RunPodClient")
    engine = WakeLLM.__new__(WakeLLM)
    engine.config = minimal_config
    engine.pod_id = minimal_config["runpod"]["pod_id"]
    engine._state = WakeLLM.STATE_STOPPED
    engine._state_lock = threading.Lock()
    engine._stop_event = threading.Event()
    engine._start_time = None
    engine._last_active_time = None
    engine.tunnel_process = None
    engine._runpod = mocker.MagicMock()
    return engine


@pytest.fixture
def flask_client(mock_engine):
    app = build_flask_app(mock_engine)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client, mock_engine


class TestWakeEndpoint:
    def test_wake_when_stopped_returns_202(self, flask_client, mocker):
        client, engine = flask_client
        mocker.patch.object(engine, "start_lifecycle", return_value=True)
        resp = client.post("/wake")
        assert resp.status_code == 202
        assert resp.get_json()["status"] == "starting"

    def test_wake_when_running_returns_200(self, flask_client):
        client, engine = flask_client
        engine._state = WakeLLM.STATE_RUNNING
        resp = client.post("/wake")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "already_running"
        assert data["pod_id"] == "abc123def456"

    def test_wake_when_starting_returns_202(self, flask_client):
        client, engine = flask_client
        engine._state = WakeLLM.STATE_STARTING
        resp = client.post("/wake")
        assert resp.status_code == 202
        assert resp.get_json()["status"] == "starting"

    def test_wake_when_stopping_returns_503(self, flask_client):
        client, engine = flask_client
        engine._state = WakeLLM.STATE_STOPPING
        resp = client.post("/wake")
        assert resp.status_code == 503
        assert resp.get_json()["status"] == "stopping"

    def test_wake_stopped_spawns_lifecycle_thread(self, flask_client, mocker):
        client, engine = flask_client
        lifecycle_started = threading.Event()

        def fake_lifecycle():
            lifecycle_started.set()

        mocker.patch.object(engine, "start_lifecycle", side_effect=fake_lifecycle)
        client.post("/wake")
        assert lifecycle_started.wait(timeout=2), "start_lifecycle was not called in a thread"


class TestStatusEndpoint:
    def test_status_returns_state_and_pod_id(self, flask_client):
        client, engine = flask_client
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == WakeLLM.STATE_STOPPED
        assert data["pod_id"] == "abc123def456"

    def test_status_reflects_running_state(self, flask_client):
        client, engine = flask_client
        engine._state = WakeLLM.STATE_RUNNING
        resp = client.get("/status")
        assert resp.get_json()["state"] == WakeLLM.STATE_RUNNING
