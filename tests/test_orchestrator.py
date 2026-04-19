"""Tests for wakellm/orchestrator.py — WakeLLM class."""
import subprocess
import threading

import pytest

from wakellm.orchestrator import WakeLLM


@pytest.fixture
def engine(minimal_config, mocker):
    """
    Fully mocked WakeLLM instance.
    All external collaborators are replaced with mocks.
    """
    mocker.patch("wakellm.orchestrator.load_config", return_value=minimal_config)
    mocker.patch("wakellm.orchestrator.validate_config")
    mocker.patch("wakellm.orchestrator.validate_pod_id")
    mock_runpod = mocker.MagicMock()
    mock_runpod.start_pod.return_value = {
        "id": "abc123def456",
        "desiredStatus": "RUNNING",
        "runtime": {
            "ports": [
                {"ip": "192.0.2.10", "isIpPublic": True,
                 "privatePort": 22, "publicPort": 43210, "type": "tcp"},
            ]
        },
    }
    mocker.patch("wakellm.orchestrator.RunPodClient", return_value=mock_runpod)
    mocker.patch("wakellm.orchestrator.start_tunnel", return_value=mocker.MagicMock(
        poll=mocker.MagicMock(return_value=None)  # process alive
    ))
    mocker.patch("wakellm.orchestrator.run_tunnel_monitor")
    mocker.patch("wakellm.orchestrator.run_idle_monitor")
    mocker.patch("time.sleep")
    return WakeLLM()


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestInit:
    def test_initial_state_is_stopped(self, engine):
        assert engine.get_state() == WakeLLM.STATE_STOPPED

    def test_pod_id_set_from_config(self, engine, minimal_config):
        assert engine.pod_id == minimal_config["runpod"]["pod_id"]

    def test_validate_config_called(self, mocker, minimal_config):
        mock_validate = mocker.patch("wakellm.orchestrator.validate_config")
        mocker.patch("wakellm.orchestrator.load_config", return_value=minimal_config)
        mocker.patch("wakellm.orchestrator.validate_pod_id")
        mocker.patch("wakellm.orchestrator.RunPodClient")
        WakeLLM()
        mock_validate.assert_called_once_with(minimal_config)

    def test_validate_pod_id_called(self, mocker, minimal_config):
        mocker.patch("wakellm.orchestrator.load_config", return_value=minimal_config)
        mocker.patch("wakellm.orchestrator.validate_config")
        mock_vpid = mocker.patch("wakellm.orchestrator.validate_pod_id")
        mocker.patch("wakellm.orchestrator.RunPodClient")
        WakeLLM()
        mock_vpid.assert_called_once_with(minimal_config["runpod"]["pod_id"])


# ---------------------------------------------------------------------------
# start_lifecycle — state transitions
# ---------------------------------------------------------------------------

class TestStartLifecycle:
    def test_transitions_stopped_to_running(self, engine):
        result = engine.start_lifecycle()
        assert result is True
        assert engine.get_state() == WakeLLM.STATE_RUNNING

    def test_idempotent_when_already_starting(self, engine, mocker):
        engine._state = WakeLLM.STATE_STARTING
        result = engine.start_lifecycle()
        assert result is False

    def test_idempotent_when_already_running(self, engine):
        engine.start_lifecycle()
        result = engine.start_lifecycle()
        assert result is False

    def test_exception_triggers_shutdown(self, engine, mocker):
        engine._runpod.start_pod.side_effect = RuntimeError("RunPod unavailable")
        mock_shutdown = mocker.patch.object(engine, "shutdown")
        engine.start_lifecycle()
        mock_shutdown.assert_called_once()

    def test_exception_returns_false(self, engine):
        engine._runpod.start_pod.side_effect = RuntimeError("fail")
        result = engine.start_lifecycle()
        assert result is False

    def test_monitor_threads_started(self, mocker, engine):
        mock_t_start = mocker.patch("threading.Thread.start")
        engine.start_lifecycle()
        # tunnel-monitor + idle-monitor threads started
        assert mock_t_start.call_count >= 2

    def test_start_pod_called(self, engine):
        engine.start_lifecycle()
        engine._runpod.start_pod.assert_called_once()

    def test_start_tunnel_called(self, engine):
        from wakellm import orchestrator as orch_module
        with pytest.MonkeyPatch.context() as mp:
            mock_tunnel = mp.setattr
            engine.start_lifecycle()
        # tunnel_process is set after success
        assert engine.tunnel_process is not None


# ---------------------------------------------------------------------------
# shutdown — state transitions and idempotency
# ---------------------------------------------------------------------------

class TestShutdown:
    def test_transitions_to_stopped(self, engine):
        engine.start_lifecycle()
        engine.shutdown()
        assert engine.get_state() == WakeLLM.STATE_STOPPED

    def test_idempotent_when_already_stopping(self, engine):
        engine._state = WakeLLM.STATE_STOPPING
        # Second call should return immediately — state stays STOPPING, no crash
        engine.shutdown()
        assert engine.get_state() == WakeLLM.STATE_STOPPING

    def test_stop_event_set(self, engine):
        engine.start_lifecycle()
        engine.shutdown()
        assert engine._stop_event.is_set()

    def test_tunnel_terminated_when_alive(self, engine, mocker):
        engine.start_lifecycle()
        mock_proc = mocker.MagicMock()
        mock_proc.poll.return_value = None  # alive
        engine.tunnel_process = mock_proc
        engine.shutdown()
        mock_proc.terminate.assert_called_once()

    def test_tunnel_not_terminated_when_already_dead(self, engine, mocker):
        engine.start_lifecycle()
        mock_proc = mocker.MagicMock()
        mock_proc.poll.return_value = 1  # already exited
        engine.tunnel_process = mock_proc
        engine.shutdown()
        mock_proc.terminate.assert_not_called()

    def test_tunnel_killed_on_terminate_timeout(self, engine, mocker):
        engine.start_lifecycle()
        mock_proc = mocker.MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.side_effect = subprocess.TimeoutExpired("ssh", 5)
        engine.tunnel_process = mock_proc
        engine.shutdown()
        mock_proc.kill.assert_called_once()

    def test_stop_pod_called_on_shutdown(self, engine):
        engine.start_lifecycle()
        engine.shutdown()
        engine._runpod.stop_pod.assert_called()


# ---------------------------------------------------------------------------
# Delegation methods
# ---------------------------------------------------------------------------

class TestDelegateMethods:
    def test_stop_pod_delegates_to_runpod(self, engine):
        engine.stop_pod()
        engine._runpod.stop_pod.assert_called_once()

    def test_get_pod_info_delegates_to_runpod(self, engine):
        engine._runpod.get_pod_info.return_value = {"id": "abc123def456"}
        result = engine.get_pod_info()
        assert result["id"] == "abc123def456"
