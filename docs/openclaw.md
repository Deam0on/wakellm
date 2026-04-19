# WakeLLM + OpenClaw Integration

[OpenClaw](https://github.com/openclaw/openclaw) is a MIT-licensed personal AI assistant
(TypeScript/Node.js) that runs as a daemon on your always-on Linux machine (Raspberry Pi,
home server, VPS, etc.) and integrates with messaging channels, cron automation, and LLM
providers.

WakeLLM and OpenClaw occupy different layers of the same stack:

```
┌────────────────────────────────────────────────────────┐
│  Always-on Linux host (Pi, server, VPS, workstation)   │
│                                                        │
│  OpenClaw daemon — assistant brain, channels, cron     │
│      │                                                 │
│      │  http://localhost:11434  (Ollama HTTP API)      │
│      │                                                 │
│  WakeLLM — SSH tunnel to RunPod pod                    │
│      │                                                 │
│      │  SSH port-forward                               │
└──────┼─────────────────────────────────────────────────┘
       │
  RunPod pod — Ollama + GPU (ephemeral, billed per use)
```

WakeLLM wakes the pod on demand, forwards Ollama to `localhost:11434`, and kills
the pod when idle. OpenClaw never knows or cares about RunPod — it just calls
`http://localhost:11434` as if Ollama were running locally.

---

## Prerequisites

- Node.js 24 (recommended) or 22.16+ installed on the host machine
- WakeLLM container built and configured (see [deployment.md](deployment.md))
- A RunPod pod with Ollama running and `WAKELLM_PORTS` including `11434:11434`

---

## Install OpenClaw

```bash
npm install -g openclaw@latest
openclaw onboard --install-daemon
```

`--install-daemon` registers OpenClaw as a `systemd` user service so it restarts
on reboot without manual intervention.

---

## Configure OpenClaw to use WakeLLM's Ollama tunnel

OpenClaw configuration lives at `~/.openclaw/openclaw.json`. To route inference
through WakeLLM's forwarded Ollama port, configure OpenClaw with an
OpenAI-compatible custom endpoint pointing at `localhost:11434`:

```json
{
  "agent": {
    "model": "openai/gemma3",
    "openai": {
      "baseURL": "http://localhost:11434/v1",
      "apiKey": "ollama"
    }
  }
}
```

> **Note:** Ollama exposes an OpenAI-compatible API at `/v1`. The `apiKey` value
> is arbitrary — Ollama ignores it but most clients require a non-empty string.
> If OpenClaw supports a native `ollama` provider in its current release, prefer
> that over the `openai` shim. Check the
> [OpenClaw models reference](https://docs.openclaw.ai/concepts/models) for the
> exact syntax of your installed version.

---

## Use case 1 — Interactive Chatbot (Open-WebUI)

This use case does not require OpenClaw at all. WakeLLM already forwards Open-WebUI:

```
WAKELLM_PORTS=11434:11434,8080:8080
```

1. Start WakeLLM: `docker run --rm --env-file env/config.env -v ~/.ssh/id_ed25519:/run/secrets/id_ed25519:ro -p 8765:8765 wakellm:latest start`
2. Open `http://localhost:8080` in a browser → Open-WebUI with Gemma (or any model
   loaded on the pod).
3. WakeLLM's idle monitor shuts the pod down automatically when no model is loaded.

---

## Use case 2 — Scheduled Digest (cron + OpenClaw)

OpenClaw has a built-in `cron` tool. A skill can fetch news, call Ollama for a
summary, and deliver the result to a channel (Telegram, Signal, email, etc.) on
a schedule — all from the Pi, with no cloud dependency beyond the RunPod pod being
awake for the duration of the task.

### Cron wrapper script

Save this to `~/bin/wakellm-digest.sh` and make it executable (`chmod +x`):

```bash
#!/usr/bin/env bash
# Wakes WakeLLM, waits for the tunnel, lets OpenClaw run the digest,
# then explicitly stops the pod for predictable billing.
set -euo pipefail

WAKELLM_CONTAINER="wakellm_digest_$$"
ENV_FILE="${WAKELLM_ENV_FILE:-${HOME}/wakellm/env/config.env}"
SSH_KEY="${WAKELLM_SSH_KEY_FILE:-${HOME}/.ssh/id_ed25519}"

# Start WakeLLM in background
docker run -d --name "$WAKELLM_CONTAINER" \
  --env-file "$ENV_FILE" \
  -v "${SSH_KEY}:/run/secrets/id_ed25519:ro" \
  -p 8765:8765 \
  wakellm:latest start

# Poll the local API until the tunnel is up (max 10 min)
echo "Waiting for WakeLLM tunnel..."
for i in $(seq 1 120); do
  if curl -sf http://localhost:8765/status | grep -q '"running"'; then
    echo "Tunnel is up."
    break
  fi
  sleep 5
done

# Run the OpenClaw skill / agent task
openclaw agent --message "Run the daily cybersecurity digest and deliver to Telegram"

# Explicit pod stop — don't wait for idle timeout
docker run --rm --env-file "$ENV_FILE" wakellm:latest stop

# Tear down the WakeLLM container
docker stop "$WAKELLM_CONTAINER" 2>/dev/null || true
docker rm   "$WAKELLM_CONTAINER" 2>/dev/null || true
```

### Add to cron

```bash
crontab -e
```

```
# Run digest every day at 06:00
0 6 * * * /home/pi/bin/wakellm-digest.sh >> /var/log/wakellm-digest.log 2>&1
```

### Billing safety

Set a short hard timeout for digest runs so a stuck script cannot leave a pod
billing overnight:

```
# in env/config.env
WAKELLM_AUTOKILL_HARD=30
```

30 minutes is a generous ceiling for a daily digest; adjust to your typical
model inference time.

---

## OpenClaw skill for a digest

A minimal AGENTS.md or skill that tells OpenClaw what "daily digest" means:

```markdown
# Daily Cybersecurity Digest

When asked to run the daily cybersecurity digest:
1. Use `browser` to fetch today's headlines from:
   - https://www.bleepingcomputer.com/
   - https://krebsonsecurity.com/
   - https://thehackernews.com/
2. Summarise the top 5 most significant items in plain English, one paragraph each.
3. Append a one-line "action required" note for any item affecting home/small-office users.
4. Deliver the result to the configured Telegram channel.
```

Place this in `~/.openclaw/workspace/skills/digest/SKILL.md` (or inline in
`AGENTS.md`). OpenClaw picks it up automatically on next restart.

---

## Further reading

- [OpenClaw getting started](https://docs.openclaw.ai/start/getting-started)
- [OpenClaw cron automation](https://docs.openclaw.ai/automation/cron-jobs)
- [OpenClaw skills](https://docs.openclaw.ai/tools/skills)
- [OpenClaw models / custom endpoints](https://docs.openclaw.ai/concepts/models)
- [WakeLLM configuration reference](configuration.md)
- [WakeLLM deployment](deployment.md)
