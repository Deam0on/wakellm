# WakeLLM

WakeLLM bridges a local always-on machine (such as a Raspberry Pi) with an ephemeral cloud GPU pod on RunPod. It provisions the remote pod on demand, establishes a local SSH port-forwarding tunnel, and shuts the pod down automatically when it is no longer in use — keeping compute costs proportional to actual usage.

---

## How It Works

1. A local cron job, CLI command, or HTTP request triggers WakeLLM.
2. WakeLLM sends a resume mutation to the RunPod API.
3. Once the pod reports ready, WakeLLM opens an SSH tunnel, forwarding configured remote ports to `localhost`.
4. Local services connect to the remote Ollama or Open WebUI as if they were running natively.
5. The idle monitor detects inactivity and tears down the pod automatically.

---

## Key Features

- **Ephemeral compute, persistent local state.** Agent memory, databases, and credentials stay on the local machine. The cloud is used only for computation.
- **SSH port forwarding.** Uses native OpenSSH to bind remote ports (Ollama, Open WebUI, etc.) to `localhost` — no extra tooling required.
- **Idle auto-kill.** Polls Ollama's `/api/ps` endpoint. Shuts down when no model has been loaded for a configurable idle period.
- **Hard uptime cap.** Unconditional shutdown after a configurable total runtime, regardless of activity.
- **Billing fail-safes.** Pod start timeout, tunnel crash detection, and exception-triggered shutdown all call `podStop` before exiting.
- **Local HTTP API.** `POST /wake` and `GET /status` endpoints for programmatic control and status polling.
- **Container-first.** Runs as a Docker container. Startup gate runs unit tests and Trivy security scans before launching the application.

---

## Quick Start

```bash
docker build -t wakellm:latest .

docker run --rm \
  -e WAKELLM_RUNPOD_API_KEY="<your-api-key>" \
  -e WAKELLM_RUNPOD_POD_ID="<your-pod-id>" \
  -e WAKELLM_SSH_KEY="$(cat ~/.ssh/id_ed25519)" \
  -e WAKELLM_PORTS="11434:11434,8080:8080" \
  wakellm:latest start
```

---

## Prerequisites

- Docker
- A RunPod account and API key
- A RunPod pod (not serverless) with `sshd` running and an SSH key registered
- An SSH private key corresponding to the key registered in the pod

---

## Documentation

| Document | Description |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Component map, state machine, lifecycle flow, threading model |
| [docs/configuration.md](docs/configuration.md) | All configuration keys — YAML and environment variable reference |
| [docs/api.md](docs/api.md) | HTTP API reference: POST /wake, GET /status |
| [docs/deployment.md](docs/deployment.md) | Docker build and run instructions, expected startup output |
| [docs/development.md](docs/development.md) | Test structure, how to add tests, design constraints |

---

## License

MIT License. See [LICENSE](LICENSE).
