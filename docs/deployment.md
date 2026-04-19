# WakeLLM Deployment

WakeLLM is designed to run as a Docker container. The normal entry point is
`start-wake.sh`, which runs the full pipeline on the host:

1. Build the container image
2. Run pytest inside an ephemeral container from the just-built image
3. Run Trivy filesystem scan (Python packages) inside a second ephemeral container
4. Run Trivy rootfs scan (OS packages) inside a third ephemeral container
5. Start WakeLLM if all checks pass

All three gate steps must pass or the script aborts before starting WakeLLM.

---

## Prerequisites

- Docker (any recent version)
- RunPod account with an API key
- A RunPod pod (not a serverless endpoint) that has `sshd` running and an SSH key configured
- An SSH private key corresponding to the key registered in RunPod

---

## Normal startup

```bash
chmod +x start-wake.sh
./start-wake.sh
```

`start-wake.sh` builds the image, runs the safety gate, then starts WakeLLM in
a persistent container named `wakellm`. It reads `env/config.env` and uses
`~/.ssh/id_ed25519` by default; override with environment variables:

```bash
WAKELLM_ENV_FILE=env/prod.env WAKELLM_SSH_KEY_FILE=/path/to/key ./start-wake.sh
```

## Build the image (manual)

```bash
docker build -t wakellm:latest .
```

The build installs Trivy from the official Aqua Security apt repository and pre-warms the Trivy vulnerability database so that gate scans are fast.

---

## Run the Container

### Recommended: use an env file (no secrets in YAML)

Copy the example file and fill in your values:

```bash
cp env/config.env.example env/config.env
```

Then run the container using `--env-file` and bind-mount your SSH key:

```bash
docker run --rm \
  --env-file env/config.env \
  -v ~/.ssh/id_ed25519:/run/secrets/id_ed25519:ro \
  -p 8765:8765 \
  wakellm:latest start
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
  --env-file env/config.env \
  -v ~/.ssh/id_ed25519:/run/secrets/id_ed25519:ro \
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

## Expected output of ./start-wake.sh

```
[1/4] Building image wakellm:latest...
... (docker build output) ...
[PASS] Image built.

[2/4] Running unit tests...
... (pytest output) ...
[PASS] All tests passed.

[3/4] Trivy: scanning installed Python packages...
... (Trivy table) ...
[PASS] No CRITICAL vulnerabilities in installed packages.

[4/4] Trivy: scanning full container filesystem...
... (Trivy table) ...
[PASS] No CRITICAL vulnerabilities in container OS.

========================================
 All checks passed — starting WakeLLM
========================================

[INFO] API server listening on http://127.0.0.1:8765 (POST /wake, GET /status)
[INFO] Waking up pod <pod-id>...
```

If any gate step fails, `start-wake.sh` exits with a non-zero status code and WakeLLM is not started.

---

## CLI commands

`start-wake.sh` accepts an action argument (default: `start`):

```bash
./start-wake.sh          # build + gate + start (default)
./start-wake.sh start    # same as above
./start-wake.sh stop     # stop the running pod (skips gate, no rebuild)
./start-wake.sh status   # print pod status     (skips gate, no rebuild)
```

Or invoke `docker run` directly without the gate:

```bash
docker run --rm --env-file env/config.env \
  -v ~/.ssh/id_ed25519:/run/secrets/id_ed25519:ro \
  -p 8765:8765 \
  wakellm:latest stop
```

---

## Persisting the Trivy Database

The Trivy DB is pre-warmed at image build time to `/var/cache/trivy`. When the image is rebuilt, the DB is refreshed. For long-running deployments where the image is not rebuilt frequently, consider volume-mounting the cache to keep the DB current without rebuilding:

```bash
docker run \
  -v trivy-cache:/var/cache/trivy \
  ...
```
