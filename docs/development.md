# WakeLLM Development Guide

---

## Project Structure

```
wakellm/
    config.py        — configuration loading, validation, accessors
    runpod.py        — RunPod GraphQL API client
    tunnel.py        — SSH tunnel subprocess management
    monitors.py      — daemon thread targets (tunnel + idle)
    api.py           — Flask HTTP API
    orchestrator.py  — WakeLLM class: state machine and lifecycle
    __main__.py      — CLI entry point
    __init__.py      — public package export (WakeLLM class)
wakellm.py           — root shim (backward compatibility)
tests/
    conftest.py      — shared pytest fixtures
    test_config.py
    test_runpod.py
    test_tunnel.py
    test_monitors.py
    test_api.py
    test_orchestrator.py
Dockerfile           — container image definition
entrypoint.sh        — container startup gate (tests + Trivy + exec)
requirements.txt     — all dependencies (runtime and test)
config.example.yaml  — configuration template
```

---

## Running Tests

Tests run inside the container as part of the startup gate. To run them manually during development, build the image and execute pytest directly:

```bash
docker build -t wakellm:dev .

# Run tests only, skip the entrypoint gate
docker run --rm wakellm:dev python3 -m pytest tests/ -v --tb=short
```

To run a specific test file or test:

```bash
docker run --rm wakellm:dev python3 -m pytest tests/test_config.py -v
docker run --rm wakellm:dev python3 -m pytest tests/test_orchestrator.py::TestShutdown -v
```

---

## Test Structure

### Fixtures (`tests/conftest.py`)

Two shared fixtures are defined; all other tests should use these rather than building their own config dicts:

| Fixture | Type | Description |
|---|---|---|
| `minimal_config` | `dict` | A complete, valid config dict. No I/O. Suitable for passing directly to any function requiring a config. |
| `mock_pod_info` | `dict` | A realistic RunPod API response dict for a running pod with SSH port `43210` on IP `192.0.2.10`. |

### Test Modules

| File | Module Under Test | Key Scenarios |
|---|---|---|
| `test_config.py` | `wakellm/config.py` | YAML loading, env-var loading, `WAKELLM_RUNPOD_API_KEY` priority, SSH key file write + `0600` permissions, validation errors, pod ID regex, `cfg()` accessor, `ollama_local_port()` |
| `test_runpod.py` | `wakellm/runpod.py` | GraphQL success and HTTP error, pod start happy path, timeout → stop + exit, polling retry until RUNNING, stop pod, get pod info |
| `test_tunnel.py` | `wakellm/tunnel.py` | SSH command structure, `-N` flag, `StrictHostKeyChecking=no`, port forwarding `-L` flags, key path expansion, missing SSH port raises `RuntimeError` |
| `test_monitors.py` | `wakellm/monitors.py` | Tunnel death triggers `shutdown_cb`, `stop_event` exits without callback, `None` proc is safe, hard timeout, idle timeout, model-loaded resets idle clock, `ConnectionError` does not start idle clock, no Ollama port prints warning |
| `test_api.py` | `wakellm/api.py` | `/wake` with all four states, `/status` response schema, daemon thread spawned for lifecycle |
| `test_orchestrator.py` | `wakellm/orchestrator.py` | Initial state, config/pod-id validation called, state transition to RUNNING, idempotency (starting/running), exception → shutdown, monitor threads started, pod stop called on shutdown, tunnel terminated, kill on SIGTERM timeout, delegate methods |

---

## Writing New Tests

### Test isolation

- Mock all I/O at the boundary: `requests.post`, `subprocess.Popen`, `time.sleep`, `time.monotonic`.
- Never make real network requests or spawn real subprocesses.
- Use `monkeypatch.delenv("WAKELLM_RUNPOD_API_KEY", raising=False)` in any test that exercises YAML loading to prevent the container environment from redirecting to the env-var loader.

### Working with threading in tests

Monitor threads block on `stop_event.wait(timeout=N)`. Replace the wait to avoid blocking:

```python
stop_event.wait = lambda timeout=None: False  # never sets, immediate return
```

Set the stop event before the test ends to ensure the thread exits:

```python
stop_event.set()
thread.join(timeout=2)
```

### Checking sys.exit()

Functions that call `sys.exit(1)` on bad input should be tested with `pytest.raises(SystemExit)`:

```python
def test_bad_pod_id_exits(monkeypatch):
    monkeypatch.delenv("WAKELLM_RUNPOD_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        validate_pod_id("bad!")
    assert exc_info.value.code == 1
```

---

## Design Constraints

These constraints are defined in `PROJECT_SCOPE.md` and must be respected:

- **No `paramiko` or `fabric`**: SSH tunnels must use the native `ssh` binary via `subprocess.Popen`.
- **Minimal dependencies**: only add to `requirements.txt` when clearly necessary; prefer stdlib.
- **No config.yaml in the image**: the container must be configured entirely through environment variables.
- **Fail-safe billing protection**: any unhandled exception in the lifecycle must result in `stop_pod()` being called.
