# WakeLLM HTTP API Reference

WakeLLM exposes a local HTTP API for triggering and monitoring the pod lifecycle. It is disabled when `api.enabled` is `false` in the configuration.

The server binds to `127.0.0.1` by default and is only accessible from the local machine.

**Base URL:** `http://127.0.0.1:8765` (configurable via `api.host` and `api.port`)

---

## Endpoints

### POST /wake

Trigger the pod lifecycle. If the orchestrator is in the `stopped` state, starts the provisioning sequence in a background thread and returns immediately.

**Request body:** none required.

**Responses:**

| HTTP Status | Body | Condition |
|---|---|---|
| `202 Accepted` | `{"status": "starting"}` | Lifecycle just kicked off (was `stopped`). |
| `202 Accepted` | `{"status": "starting"}` | Already in the process of starting. |
| `200 OK` | `{"status": "already_running", "pod_id": "<pod_id>"}` | Pod is already running. |
| `503 Service Unavailable` | `{"status": "stopping", "message": "Pod is currently shutting down, retry shortly."}` | Shutdown in progress; retry after a few seconds. |

**Example:**
```bash
curl -s -X POST http://127.0.0.1:8765/wake | jq .
```

```json
{
  "status": "starting"
}
```

---

### GET /status

Query the current state of the orchestrator.

**Request body:** none.

**Response:** `200 OK` always.

| Field | Type | Description |
|---|---|---|
| `state` | string | One of: `stopped`, `starting`, `running`, `stopping` |
| `pod_id` | string | The configured RunPod pod ID |

**Example:**
```bash
curl -s http://127.0.0.1:8765/status | jq .
```

```json
{
  "state": "running",
  "pod_id": "6068y77xfq1rux"
}
```

---

## State Values

| State | Description |
|---|---|
| `stopped` | No pod running. Ready to accept `/wake`. |
| `starting` | Pod resume sent; waiting for the pod to be ready and the SSH tunnel to connect. |
| `running` | Tunnel and monitors are active. |
| `stopping` | Shutdown initiated; cleaning up resources. |

---

## Notes

- The `/wake` endpoint returns immediately; provisioning happens asynchronously. Poll `/status` to track progress.
- The API server runs in a daemon thread. It starts before the lifecycle begins so that `/wake` is reachable even during pod boot.
- If Flask is not installed, the API is silently disabled and a warning is printed to stdout.
- All API responses use `Content-Type: application/json`.
