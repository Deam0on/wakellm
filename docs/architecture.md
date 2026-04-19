# WakeLLM Architecture

## Overview

WakeLLM is a Python orchestrator that bridges a local always-on Linux machine (Raspberry Pi, home server, VPS, workstation, etc.) with an ephemeral cloud GPU pod on RunPod. It provisions the remote pod on demand, establishes a local SSH port-forwarding tunnel, monitors activity, and shuts the pod down automatically when it is no longer needed — preventing runaway billing.

---

## Component Map

```
                         +-----------------------+
  HTTP client  --------> | Flask API             |  POST /wake, GET /status
  (local only)           | wakellm/api.py        |
                         +-----------+-----------+
                                     |
                         +-----------v-----------+
                         | WakeLLM (orchestrator)|
                         | wakellm/orchestrator.py|
                         +--+------+------+------+
                            |      |      |
            +---------------+  +---+  +--+---------------+
            |                  |      |                   |
  +---------v-------+  +-------v--+  +---v-----------+  +-v-----------+
  | RunPodClient    |  | start_   |  | run_tunnel_   |  | run_idle_   |
  | wakellm/        |  | tunnel() |  | monitor()     |  | monitor()   |
  | runpod.py       |  | tunnel.py|  | monitors.py   |  | monitors.py |
  | (GraphQL API)   |  | (ssh     |  | (daemon       |  | (daemon     |
  +-----------------+  |  Popen)  |  |  thread)      |  |  thread)    |
                        +----------+  +---------------+  +-------------+
                             |                |                |
                             v                v                v
                        RunPod pod      stop_event        stop_event
                        SSH port        set on             set on
                        (native ssh)    tunnel death       idle/timeout
```

---

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `wakellm/config.py` | Load and validate configuration from YAML or environment variables. Expose typed accessor helpers. |
| `wakellm/runpod.py` | All RunPod GraphQL API calls: resume pod, stop pod, poll pod status. |
| `wakellm/tunnel.py` | Launch and return the native `ssh -N -L` subprocess. |
| `wakellm/monitors.py` | Two daemon-thread targets: tunnel health monitor and Ollama idle monitor. |
| `wakellm/api.py` | Build the Flask application and start it in a daemon thread. |
| `wakellm/orchestrator.py` | `WakeLLM` class: owns the state machine, coordinates the lifecycle, holds references to all running components. |
| `wakellm/__main__.py` | CLI entry point (`start`, `stop`, `status`). |
| `wakellm.py` | Root-level shim for backward compatibility with `python wakellm.py start`. |

---

## State Machine

The orchestrator enforces a strict linear state machine guarded by a `threading.Lock`.

```
  stopped  -->  starting  -->  running  -->  stopping  -->  stopped
```

| State | Meaning |
|---|---|
| `stopped` | Initial state. No pod running, no tunnel. |
| `starting` | Pod resume sent; waiting for RUNNING + SSH boot. |
| `running` | Tunnel active; monitor threads alive. |
| `stopping` | Shutdown initiated; tearing down resources. |

Transitions are only permitted in the forward direction. Calling `start_lifecycle()` when the state is `starting` or `running` is a no-op (returns `False`). Calling `shutdown()` when the state is already `stopping` is a no-op (idempotent).

---

## Lifecycle Flow

```
start_lifecycle()
  |
  +-- set state STARTING
  |
  +-- RunPodClient.start_pod()
  |     +-- podResume GraphQL mutation
  |     +-- poll get_pod_info() until desiredStatus == RUNNING and runtime != null
  |     +-- abort to stop_pod() + sys.exit(1) if pod_start_timeout_minutes exceeded
  |
  +-- sleep(ssh_boot_wait_seconds)    # let sshd fully start inside the container
  |
  +-- start_tunnel(config, pod_info)  # returns Popen; blocks until ssh exits or killed
  |
  +-- set state RUNNING
  |
  +-- spawn tunnel-monitor thread     # polls proc.poll() every 5 s
  +-- spawn idle-monitor thread       # polls Ollama /api/ps every ollama_poll_interval_seconds
  |
  return True
```

Either monitor calls `shutdown()` when its condition is met, which:
1. Sets `stop_event` (unblocks both monitor loops immediately)
2. Terminates the SSH tunnel subprocess (SIGTERM, SIGKILL after 5 s)
3. Calls `RunPodClient.stop_pod()` to halt billing
4. Sets state to `STOPPED`

---

## Threading Model

| Thread | Type | Name | Lifetime |
|---|---|---|---|
| Main thread | — | — | Entire process |
| Flask API server | daemon | `api-server` | Until process exits |
| Tunnel monitor | daemon | `tunnel-monitor` | RUNNING until shutdown |
| Idle monitor | daemon | `idle-monitor` | RUNNING until shutdown |
| Lifecycle (via `/wake`) | daemon | `lifecycle` | One shot |

All daemon threads are automatically killed when the main thread exits.

Communication between threads uses two primitives:
- `threading.Event` (`stop_event`): set by `shutdown()` to unblock `stop_event.wait(timeout=N)` calls inside both monitors simultaneously.
- `threading.Lock` (`_state_lock`): protects all reads and writes to `_state`.

---

## Port Forwarding

Each entry in the `ports` config list produces one `-L` flag on the `ssh` command:

```
-L <local_port>:localhost:<remote_port>
```

This makes the remote pod's services reachable on `localhost` of the local machine. No external network exposure occurs — the tunnel binds to `localhost` on the remote side.

---

## Fail-Safe Billing Protection

Multiple layers guard against a pod running unattended and accruing unexpected charges:

1. **Pod start timeout**: if the pod does not reach RUNNING within `startup.pod_start_timeout_minutes`, it is stopped and the process exits with code 1.
2. **Tunnel crash detection**: if the SSH subprocess exits unexpectedly, `shutdown()` is called immediately.
3. **Idle auto-kill**: if Ollama reports no loaded models for `autokill.idle_timeout_minutes`, `shutdown()` is called.
4. **Hard uptime cap**: regardless of activity, `shutdown()` is called after `autokill.hard_timeout_minutes` of total runtime.
5. **`stop_pod()` is always called**: even on exceptions during `start_lifecycle()`, `shutdown()` is invoked in the `except` block.
