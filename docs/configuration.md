# WakeLLM Configuration Reference

WakeLLM is configured **exclusively through environment variables**. No YAML file is used or required.

Copy `env/config.env.example` to `env/config.env`, fill in your values, and pass it to Docker:

```bash
cp env/config.env.example env/config.env
# edit env/config.env with your API key, pod id, SSH key path, and ports
docker run --rm \
  --env-file env/config.env \
  -v ~/.ssh/id_ed25519:/run/secrets/id_ed25519:ro \
  -p 8765:8765 \
  wakellm:latest start
```

`env/config.env` is listed in `.gitignore` — it will never be committed.

---

## Full Variable Reference

| Environment Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `WAKELLM_RUNPOD_API_KEY` | string | — | Yes | RunPod API key (Account → API Keys) |
| `WAKELLM_RUNPOD_POD_ID` | string | — | Yes | RunPod pod id (e.g. `6068y77xfq1rux`) |
| `WAKELLM_SSH_KEY_PATH` | path | — | Yes* | Path to SSH private key inside the container |
| `WAKELLM_SSH_KEY` | string | — | Yes* | Raw SSH private key content (written to `/tmp/wakellm_ssh_key` at 0600) |
| `WAKELLM_PORTS` | csv | — | Yes | Comma-separated `local:remote` port pairs (e.g. `11434:11434,8080:8080`) |
| `WAKELLM_STARTUP_TIMEOUT` | integer | `5` | No | Minutes to wait for pod to reach RUNNING |
| `WAKELLM_STARTUP_BOOT_WAIT` | integer | `10` | No | Seconds to wait after RUNNING before SSH |
| `WAKELLM_AUTOKILL_IDLE` | integer | `15` | No | Idle minutes before auto-shutdown |
| `WAKELLM_AUTOKILL_HARD` | integer | `120` | No | Hard uptime cap in minutes |
| `WAKELLM_AUTOKILL_POLL` | integer | `30` | No | Ollama poll interval in seconds |
| `WAKELLM_AUTOKILL_OLLAMA_PORT` | integer | `11434` | No | Remote Ollama port (must match an entry in `WAKELLM_PORTS`) |
| `WAKELLM_API_ENABLED` | boolean | `true` | No | Enable/disable the local HTTP API |
| `WAKELLM_API_HOST` | string | `127.0.0.1` | No | API bind address — keep as `127.0.0.1`; never expose externally |
| `WAKELLM_API_PORT` | integer | `8765` | No | API port |

\* Exactly one of `WAKELLM_SSH_KEY_PATH` or `WAKELLM_SSH_KEY` is required.

---

## SSH Key

**Option A — bind-mount (recommended):** keep the key on the Pi filesystem and mount it read-only:

```bash
-v /home/pi/.ssh/id_ed25519:/run/secrets/id_ed25519:ro
# in env/config.env:
WAKELLM_SSH_KEY_PATH=/run/secrets/id_ed25519
```

**Option B — raw content:** pass the key directly as an environment variable. The container writes it to `/tmp/wakellm_ssh_key` with `0600` permissions. Not recommended for production; prefer Option A.

---

## Port Mappings (`WAKELLM_PORTS`)

Comma-separated `local:remote` pairs. Whitespace around commas and colons is stripped.

```
WAKELLM_PORTS=11434:11434,8080:8080
```

- `11434:11434` — forwards Ollama on the pod to `localhost:11434` on the Pi
- `8080:8080` — forwards Open-WebUI on the pod to `localhost:8080` on the Pi

---

## Boolean Values

`WAKELLM_API_ENABLED` accepts: `true`, `1`, `yes` (enabled) or `false`, `0`, `no` (disabled). Case-insensitive.
