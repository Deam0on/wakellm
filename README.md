# WakeLLM

**Summon a datacenter GPU to your local network, and only pay for the minutes you use.**

WakeLLM bridges the gap between low-power, always-on home servers (like a Raspberry Pi) and high-power ephemeral cloud GPUs (like RunPod). It allows you to keep your sensitive data, agent memory, and API keys securely on your local network, while dynamically spinning up massive cloud compute only when it is needed.

When you send a chat message or a scheduled agent (like OpenClaw) wakes up, WakeLLM provisions a cloud GPU, establishes a secure SSH tunnel to your local machine, and exposes the remote Ollama and Open WebUI services as if they were running natively on your `localhost`. When the task is done, the instance is destroyed.

### Key Features
* **Ephemeral Compute, Persistent State:** Keep your agent's memory, databases, and workflow logic locked safely on your local LAN. The cloud is strictly used as a temporary "brain."
* **Zero-Config Tunneling:** Automatically binds remote cloud ports (e.g., 11434 for Ollama, 8080 for Open WebUI) to your local machine.
* **Smart Idle Auto-Kill:** Monitors API traffic and web socket connections. If your agent finishes its task or you stop chatting for a predefined time, WakeLLM automatically shuts down the remote pod to prevent runaway billing.
* **Agent Framework Ready:** Plugs seamlessly into tools like OpenClaw, AutoGen, and CrewAI without needing to refactor their network logic.

### Architecture Workflow
1. **Trigger:** A local CRON job or CLI command tells WakeLLM to wake up.
2. **Provision:** WakeLLM hits the RunPod API to start your pre-configured GPU pod.
3. **Tunnel:** Once the pod is alive, WakeLLM retrieves the ephemeral IP and establishes a reverse SSH tunnel.
4. **Execution:** Local services (OpenClaw, scripts) connect to `http://localhost:11434` seamlessly.
5. **Terminate:** The auto-kill daemon detects inactivity and tears down the infrastructure.

### Prerequisites
* A local machine (Raspberry Pi, old laptop, or Mini PC) running Linux/macOS.
* Python 3.10+
* A RunPod account and API Key.
* A pre-configured RunPod Network Volume with your LLM tools (Ollama / Open WebUI) installed.

### Quick Start (Coming Soon)
```bash
git clone [https://github.com/yourusername/WakeLLM.git](https://github.com/yourusername/WakeLLM.git)
cd WakeLLM
pip install -r requirements.txt

# Configure your API keys and Pod ID
cp config.example.yaml config.yaml
nano config.yaml

# Summon the GPU and start the tunnel
wakellm start
