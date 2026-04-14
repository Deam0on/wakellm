"""Tests for wakellm/monitors.py"""
import threading
import time

import pytest
import requests

from wakellm.monitors import run_tunnel_monitor, run_idle_monitor


def _make_stop_event(auto_stop_after=None):
    """Return a threading.Event, optionally set after a delay (in a daemon thread)."""
    event = threading.Event()
    if auto_stop_after is not None:
        def _setter():
            time.sleep(auto_stop_after)
            event.set()
        threading.Thread(target=_setter, daemon=True).start()
    return event


# ---------------------------------------------------------------------------
# run_tunnel_monitor
# ---------------------------------------------------------------------------

class TestTunnelMonitor:
    def test_dead_tunnel_calls_shutdown(self, mocker):
        shutdown_called = threading.Event()
        stop_event = threading.Event()
        # Make wait() return False immediately so the loop body runs without blocking.
        stop_event.wait = lambda timeout=None: False

        mock_proc = mocker.MagicMock()
        mock_proc.poll.return_value = 1  # process has exited

        def fake_shutdown():
            shutdown_called.set()

        t = threading.Thread(
            target=run_tunnel_monitor,
            args=(stop_event, lambda: mock_proc, fake_shutdown),
            daemon=True,
        )
        t.start()
        assert shutdown_called.wait(timeout=2), "shutdown_cb was not called"

    def test_stop_event_exits_without_shutdown(self, mocker):
        shutdown_called = threading.Event()
        stop_event = threading.Event()
        mock_proc = mocker.MagicMock()
        mock_proc.poll.return_value = None  # tunnel alive

        t = threading.Thread(
            target=run_tunnel_monitor,
            args=(stop_event, lambda: mock_proc, lambda: shutdown_called.set()),
            daemon=True,
        )
        t.start()
        stop_event.set()
        t.join(timeout=2)
        assert not shutdown_called.is_set()

    def test_none_proc_does_not_call_shutdown(self, mocker):
        shutdown_called = threading.Event()
        stop_event = _make_stop_event(auto_stop_after=0.05)

        t = threading.Thread(
            target=run_tunnel_monitor,
            args=(stop_event, lambda: None, lambda: shutdown_called.set()),
            daemon=True,
        )
        t.start()
        t.join(timeout=2)
        assert not shutdown_called.is_set()


# ---------------------------------------------------------------------------
# run_idle_monitor
# ---------------------------------------------------------------------------

class TestIdleMonitor:
    def _run_monitor(self, config, stop_event, start_time_val, shutdown_cb):
        """Helper: run idle monitor in a thread with lambda-wrapped state."""
        t = threading.Thread(
            target=run_idle_monitor,
            args=(
                config,
                stop_event,
                lambda: start_time_val[0],
                lambda t: None,
                shutdown_cb,
            ),
            daemon=True,
        )
        t.start()
        return t

    def test_hard_timeout_calls_shutdown(self, minimal_config, mocker):
        # Set hard timeout to 1 second worth of minutes (use tiny value in config)
        minimal_config["autokill"]["hard_timeout_minutes"] = 1
        minimal_config["autokill"]["ollama_poll_interval_seconds"] = 0  # poll immediately

        shutdown_called = threading.Event()
        stop_event = threading.Event()
        # start_time set far in the past so hard timeout is already exceeded
        fake_start = [time.monotonic() - 999]

        mocker.patch("requests.get", side_effect=requests.exceptions.ConnectionError)

        t = self._run_monitor(minimal_config, stop_event, fake_start,
                              lambda: shutdown_called.set() or stop_event.set())
        assert shutdown_called.wait(timeout=3), "shutdown_cb not called for hard timeout"

    def test_idle_timeout_calls_shutdown(self, minimal_config, mocker):
        minimal_config["autokill"]["idle_timeout_minutes"] = 1
        minimal_config["autokill"]["ollama_poll_interval_seconds"] = 0
        minimal_config["autokill"]["hard_timeout_minutes"] = 9999

        shutdown_called = threading.Event()
        stop_event = threading.Event()
        fake_start = [time.monotonic()]

        # Ollama responds with no models loaded
        mock_resp = mocker.MagicMock()
        mock_resp.json.return_value = {"models": []}
        mocker.patch("requests.get", return_value=mock_resp)

        # Trick the idle duration to be > timeout by patching time.monotonic
        # to return values N seconds apart
        real_monotonic = time.monotonic
        call_count = {"n": 0}

        def fake_monotonic():
            call_count["n"] += 1
            # After a few calls, simulate 2+ minutes of wall time
            return real_monotonic() + (call_count["n"] * 100)

        mocker.patch("wakellm.monitors.time.monotonic", side_effect=fake_monotonic)

        t = self._run_monitor(minimal_config, stop_event, fake_start,
                              lambda: shutdown_called.set() or stop_event.set())
        assert shutdown_called.wait(timeout=3), "shutdown_cb not called for idle timeout"

    def test_model_loaded_resets_idle_clock(self, minimal_config, mocker):
        minimal_config["autokill"]["idle_timeout_minutes"] = 9999
        minimal_config["autokill"]["hard_timeout_minutes"] = 9999
        minimal_config["autokill"]["ollama_poll_interval_seconds"] = 0

        shutdown_called = threading.Event()
        stop_event = _make_stop_event(auto_stop_after=0.1)
        fake_start = [time.monotonic()]
        last_active = [None]

        mock_resp = mocker.MagicMock()
        mock_resp.json.return_value = {"models": [{"name": "llama3"}]}
        mocker.patch("requests.get", return_value=mock_resp)

        t = threading.Thread(
            target=run_idle_monitor,
            args=(
                minimal_config,
                stop_event,
                lambda: fake_start[0],
                lambda t: last_active.__setitem__(0, t),
                lambda: shutdown_called.set(),
            ),
            daemon=True,
        )
        t.start()
        t.join(timeout=2)
        assert not shutdown_called.is_set()
        assert last_active[0] is not None  # set_last_active was called

    def test_connection_error_does_not_trigger_idle(self, minimal_config, mocker):
        minimal_config["autokill"]["idle_timeout_minutes"] = 1
        minimal_config["autokill"]["hard_timeout_minutes"] = 9999
        minimal_config["autokill"]["ollama_poll_interval_seconds"] = 0

        shutdown_called = threading.Event()
        stop_event = _make_stop_event(auto_stop_after=0.1)
        fake_start = [time.monotonic()]

        mocker.patch("requests.get", side_effect=requests.exceptions.ConnectionError)

        # Even though idle_timeout is tiny, no idle clock starts on ConnectionError
        t = threading.Thread(
            target=run_idle_monitor,
            args=(
                minimal_config, stop_event,
                lambda: fake_start[0], lambda t: None,
                lambda: shutdown_called.set(),
            ),
            daemon=True,
        )
        t.start()
        t.join(timeout=2)
        assert not shutdown_called.is_set()

    def test_no_ollama_port_prints_warning(self, minimal_config, mocker, capsys):
        minimal_config["ports"] = ["8080:8080"]  # no 11434 mapping
        minimal_config["autokill"]["hard_timeout_minutes"] = 9999
        minimal_config["autokill"]["ollama_poll_interval_seconds"] = 0

        stop_event = _make_stop_event(auto_stop_after=0.05)
        t = threading.Thread(
            target=run_idle_monitor,
            args=(
                minimal_config, stop_event,
                lambda: time.monotonic(), lambda t: None,
                lambda: None,
            ),
            daemon=True,
        )
        t.start()
        t.join(timeout=2)
        captured = capsys.readouterr()
        assert "Idle monitor disabled" in captured.out
