# WakeLLM Deployment

WakeLLM is designed to run as a Docker container. The container image performs three safety gates on every startup before launching the application:

1. Unit tests (pytest)
2. Trivy filesystem scan — CRITICAL vulnerabilities in installed Python packages
3. Trivy rootfs scan — CRITICAL vulnerabilities in OS packages

All three must pass for the application to start.

---

## Prerequisites

- Docker (any recent version)
- RunPod account with an API key
- A RunPod pod (not a serverless endpoint) that has `sshd` running and an SSH key configured
- An SSH private key corresponding to the key registered in RunPod

---

## Build the Image

```bash
docker build -t wakellm:latest .
```

The build installs Trivy from the official Aqua Security apt repository and pre-warms the Trivy vulnerability database so that startup scans are fast.

---

## Run the Container

### Required Environment Variables

| Variable | Description |
|---|---|
| `WAKELLM_RUNPOD_API_KEY` | Your RunPod API key |
| `WAKELLM_RUNPOD_POD_ID` | The ID of the pod to resume (e.g., `6068y77xfq1rux`) |
| `WAKELLM_SSH_KEY_PATH` or `WAKELLM_SSH_KEY` | SSH private key (see below) |
| `WAKELLM_PORTS` | Comma-separated `local:remote` port mappings (e.g., `11434:11434,8080:8080`) |

### SSH Key Options

**Option A — bind-mount the key file:**
```bash
docker run \
  -v ~/.ssh/id_ed25519:/run/secrets/id_ed25519:ro \
  -e WAKELLM_SSH_KEY_PATH=/run/secrets/id_ed25519 \
  ...
```

**Option B — pass key content as an environment variable:**
```bash
docker run \
  -e WAKELLM_SSH_KEY="$(cat ~/.ssh/id_ed25519)" \
  ...
```
The key is written to `/tmp/wakellm_ssh_key` with `0600` permissions inside the container.

---

## Full docker run Example

```bash
docker run --rm \
  -e WAKELLM_RUNPOD_API_KEY="<your-api-key>" \
  -e WAKELLM_RUNPOD_POD_ID="<your-pod-id>" \
  -e WAKELLM_SSH_KEY="$(cat ~/.ssh/id_ed25519)" \
  -e WAKELLM_PORTS="11434:11434,8080:8080" \
  -p 8765:8765 \
  wakellm:latest start
```

Port `8765` must be published with `-p 8765:8765` if you want to reach the HTTP API from outside the container. Note that `api.host` defaults to `127.0.0.1`, which means the API is only accessible from within the container's network namespace unless you also set `WAKELLM_API_HOST=0.0.0.0`.

---

## Optional Environment Variables

See [configuration.md](configuration.md) for a full reference. Key optional variables:

| Variable | Default | Description |
|---|---|---|
| `WAKELLM_STARTUP_TIMEOUT` | `5` | Minutes to wait for pod to reach RUNNING |
| `WAKELLM_STARTUP_BOOT_WAIT` | `10` | Seconds to wait before SSH after pod is RUNNING |
| `WAKELLM_AUTOKILL_IDLE` | `15` | Idle minutes before auto-shutdown |
| `WAKELLM_AUTOKILL_HARD` | `120` | Hard uptime cap in minutes |
| `WAKELLM_API_HOST` | `127.0.0.1` | Set to `0.0.0.0` to expose the API outside the container |
| `WAKELLM_API_PORT` | `8765` | API port |

---

## Expected Startup Output

```
========================================
 WakeLLM Container Startup Gate
========================================

[1/3] Running unit tests...
... (pytest output) ...
[PASS] All tests passed.

[2/3] Trivy: scanning installed Python packages...
... (Trivy table) ...
[PASS] No CRITICAL vulnerabilities in installed packages.

[3/3] Trivy: scanning full container filesystem...
... (Trivy table) ...
[PASS] No CRITICAL vulnerabilities in container OS.

========================================
 All checks passed — starting WakeLLM
========================================

[INFO] API server listening on http://127.0.0.1:8765 (POST /wake, GET /status)
[INFO] Waking up pod <pod-id>...
```

If any gate step fails, the container exits with a non-zero status code without starting the application.

---

## CLI Commands

The container's `CMD` defaults to `start`. You can override it:

```bash
# Start the pod and tunnel (default)
docker run ... wakellm:latest start

# Stop the currently running pod (sends podStop mutation; no tunnel required)
docker run ... wakellm:latest stop

# Print the pod's current status from the RunPod API
docker run ... wakellm:latest status
```

---

## Persisting the Trivy Database

The Trivy DB is pre-warmed at image build time to `/var/cache/trivy`. When the image is rebuilt, the DB is refreshed. For long-running deployments where the image is not rebuilt frequently, consider volume-mounting the cache to keep the DB current without rebuilding:

```bash
docker run \
  -v trivy-cache:/var/cache/trivy \
  ...
```
