# WakeLLM Configuration Reference

WakeLLM can be configured using a YAML file or entirely through environment variables. Environment variables take priority: if `WAKELLM_RUNPOD_API_KEY` is set, the YAML file is ignored.

---

## Quick Reference

| YAML Path | Environment Variable | Type | Default | Required |
|---|---|---|---|---|
| `runpod.api_key` | `WAKELLM_RUNPOD_API_KEY` | string | — | Yes |
| `runpod.pod_id` | `WAKELLM_RUNPOD_POD_ID` | string | — | Yes |
| `ssh.key_path` | `WAKELLM_SSH_KEY_PATH` | path | — | Yes* |
| _(no YAML equivalent)_ | `WAKELLM_SSH_KEY` | string | — | Yes* |
| `ports` | `WAKELLM_PORTS` | list / csv | — | Yes |
| `startup.pod_start_timeout_minutes` | `WAKELLM_STARTUP_TIMEOUT` | integer | `5` | No |
| `startup.ssh_boot_wait_seconds` | `WAKELLM_STARTUP_BOOT_WAIT` | integer | `10` | No |
| `autokill.idle_timeout_minutes` | `WAKELLM_AUTOKILL_IDLE` | integer | `15` | No |
| `autokill.hard_timeout_minutes` | `WAKELLM_AUTOKILL_HARD` | integer | `120` | No |
| `autokill.ollama_poll_interval_seconds` | `WAKELLM_AUTOKILL_POLL` | integer | `30` | No |
| `autokill.ollama_remote_port` | `WAKELLM_AUTOKILL_OLLAMA_PORT` | integer | `11434` | No |
| `api.enabled` | `WAKELLM_API_ENABLED` | boolean | `true` | No |
| `api.host` | `WAKELLM_API_HOST` | string | `127.0.0.1` | No |
| `api.port` | `WAKELLM_API_PORT` | integer | `8765` | No |

\* One of `WAKELLM_SSH_KEY_PATH` or `WAKELLM_SSH_KEY` is required.

---

## YAML Configuration

Copy `config.example.yaml` to `config.yaml` and edit it.

```yaml
runpod:
  api_key: "YOUR_RUNPOD_API_KEY"
  pod_id: "YOUR_POD_ID"

ssh:
  key_path: "~/.ssh/id_ed25519"

ports:
  - "11434:11434"   # Ollama API
  - "8080:8080"     # Open WebUI

startup:
  pod_start_timeout_minutes: 5
  ssh_boot_wait_seconds: 10

autokill:
  idle_timeout_minutes: 15
  hard_timeout_minutes: 120
  ollama_poll_interval_seconds: 30
  ollama_remote_port: 11434

api:
  enabled: true
  host: "127.0.0.1"
  port: 8765
```

---

## Environment Variable Configuration

All required values can be supplied as environment variables. When `WAKELLM_RUNPOD_API_KEY` is set, the YAML file is not read.

### SSH Key

Two mutually exclusive options are available:

**Option A — file path (bind-mount or pre-existing file):**
```bash
-e WAKELLM_SSH_KEY_PATH=/run/secrets/id_ed25519
```

**Option B — raw key content (base64-encoded or plain text):**
```bash
-e WAKELLM_SSH_KEY="$(cat ~/.ssh/id_ed25519)"
```
The key content is written to `/tmp/wakellm_ssh_key` with permissions `0600`. It must be a valid PEM-format private key.

### Port Mappings

`WAKELLM_PORTS` is a comma-separated list of `local:remote` pairs:
```bash
-e WAKELLM_PORTS="11434:11434,8080:8080"
```
Whitespace around commas and colons is stripped.

### Boolean Values

`WAKELLM_API_ENABLED` accepts: `true`, `1`, `yes` (enabled) or `false`, `0`, `no` (disabled). Case-insensitive.

---

## Field Details

### `runpod.api_key` / `WAKELLM_RUNPOD_API_KEY`

Your RunPod API key. Found in the RunPod dashboard under Account > API Keys.

### `runpod.pod_id` / `WAKELLM_RUNPOD_POD_ID`

The ID of the RunPod pod to resume. Must match the format: lowercase alphanumeric and hyphens, 8-20 characters total, not starting or ending with a hyphen (e.g., `6068y77xfq1rux`).

### `ssh.key_path` / `WAKELLM_SSH_KEY_PATH`

Absolute or `~`-prefixed path to the SSH private key registered in your RunPod account for the pod. The key must be accessible to the process at startup.

### `ports` / `WAKELLM_PORTS`

Defines the port-forwarding rules for the SSH tunnel. Each entry maps a local port to a remote port on the pod. The remote services must be listening on `localhost` inside the pod.

### `startup.pod_start_timeout_minutes` / `WAKELLM_STARTUP_TIMEOUT`

Maximum time to wait for the pod to reach `RUNNING` status after sending the resume mutation. If the pod is not ready within this window, it is stopped via the API and the process exits with code 1.

### `startup.ssh_boot_wait_seconds` / `WAKELLM_STARTUP_BOOT_WAIT`

Seconds to sleep after the pod reports `RUNNING` before attempting the SSH connection. This gives the `sshd` daemon inside the container time to fully start.

### `autokill.idle_timeout_minutes` / `WAKELLM_AUTOKILL_IDLE`

If Ollama's `/api/ps` endpoint reports no loaded models for this many consecutive minutes, WakeLLM shuts down the pod. The idle clock starts only after Ollama is first reachable (connection errors during boot are ignored).

### `autokill.hard_timeout_minutes` / `WAKELLM_AUTOKILL_HARD`

Unconditional uptime cap. WakeLLM will initiate shutdown after this many minutes regardless of Ollama activity. Set to a high value to effectively disable it.

### `autokill.ollama_poll_interval_seconds` / `WAKELLM_AUTOKILL_POLL`

How often (in seconds) the idle monitor polls Ollama's `/api/ps` endpoint.

### `autokill.ollama_remote_port` / `WAKELLM_AUTOKILL_OLLAMA_PORT`

The remote port that Ollama listens on inside the pod. Used to determine which local forwarded port to poll. Must match one of the remote ports in `ports`.

### `api.enabled` / `WAKELLM_API_ENABLED`

Set to `false` to disable the local HTTP API entirely. WakeLLM will only accept CLI commands.

### `api.host` / `WAKELLM_API_HOST`

Address on which the Flask API server listens. Defaults to `127.0.0.1` (localhost only). Do not expose this to external networks.

### `api.port` / `WAKELLM_API_PORT`

TCP port for the local API server (default: `8765`).
