#!/usr/bin/env bash
# WakeLLM host-side pipeline.
#
# Usage:
#   ./start-wake.sh [start|stop|status]
#
# Environment overrides (all optional):
#   WAKELLM_ENV_FILE      path to the env file   (default: env/config.env)
#   WAKELLM_SSH_KEY_FILE  path to SSH private key (default: ~/.ssh/id_ed25519)
#   WAKELLM_IMAGE         Docker image name        (default: wakellm:latest)
#   WAKELLM_API_PORT      host port for the API    (default: 8765)
#
set -euo pipefail

IMAGE="${WAKELLM_IMAGE:-wakellm:latest}"
ENV_FILE="${WAKELLM_ENV_FILE:-env/config.env}"
SSH_KEY_FILE="${WAKELLM_SSH_KEY_FILE:-${HOME}/.ssh/id_ed25519}"
API_PORT="${WAKELLM_API_PORT:-8765}"
ACTION="${1:-start}"

# ---------------------------------------------------------------------------
# stop / status: no rebuild or gate needed — forward straight to the container
# ---------------------------------------------------------------------------
if [[ "$ACTION" == "stop" || "$ACTION" == "status" ]]; then
  docker run --rm \
    --env-file "$ENV_FILE" \
    "$IMAGE" "$ACTION"
  exit $?
fi

# ---------------------------------------------------------------------------
# start: full build → gate → run pipeline
# ---------------------------------------------------------------------------

# Confirm the env file and SSH key are present before spending time on a build
if [[ ! -f "$ENV_FILE" ]]; then
  echo "[ERROR] Env file not found: $ENV_FILE"
  echo "        Copy env/config.env.example to env/config.env and fill in your values."
  exit 1
fi

if [[ ! -f "$SSH_KEY_FILE" ]]; then
  echo "[ERROR] SSH key not found: $SSH_KEY_FILE"
  echo "        Override with: WAKELLM_SSH_KEY_FILE=/path/to/key ./start-wake.sh"
  exit 1
fi

# ---------------------------------------------------------------------------
# 1. Build
# ---------------------------------------------------------------------------
echo ""
echo "[1/4] Building image ${IMAGE}..."
docker build -t "$IMAGE" .
echo "[PASS] Image built."

# ---------------------------------------------------------------------------
# 2. Unit tests (ephemeral container — no secrets needed)
# ---------------------------------------------------------------------------
echo ""
echo "[2/4] Running unit tests..."
docker run --rm \
  --entrypoint python3 \
  "$IMAGE" \
  -m pytest tests/ -v --tb=short
echo "[PASS] All tests passed."

# ---------------------------------------------------------------------------
# 3. Trivy: filesystem scan (Python packages in /app)
# ---------------------------------------------------------------------------
echo ""
echo "[3/4] Trivy: scanning installed Python packages..."
docker run --rm \
  --entrypoint trivy \
  --mount type=volume,source=wakellm-trivy-cache,target=/var/cache/trivy \
  "$IMAGE" \
  fs \
    --cache-dir /var/cache/trivy \
    --scanners vuln \
    --severity CRITICAL \
    --exit-code 1 \
    --no-progress \
    /app
echo "[PASS] No CRITICAL vulnerabilities in installed packages."

# ---------------------------------------------------------------------------
# 4. Trivy: full rootfs scan (OS packages + system libraries)
#    --skip-files excludes the Trivy binary itself; it is a scanning tool and
#    is not reachable at application runtime.
# ---------------------------------------------------------------------------
echo ""
echo "[4/4] Trivy: scanning full container filesystem..."
docker run --rm \
  --entrypoint trivy \
  --mount type=volume,source=wakellm-trivy-cache,target=/var/cache/trivy \
  "$IMAGE" \
  rootfs \
    --cache-dir /var/cache/trivy \
    --scanners vuln \
    --severity CRITICAL \
    --exit-code 1 \
    --no-progress \
    --skip-files /usr/bin/trivy \
    /
echo "[PASS] No CRITICAL vulnerabilities in container OS."

# ---------------------------------------------------------------------------
# 5. Start WakeLLM
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " All checks passed — starting WakeLLM"
echo "========================================"
echo ""

docker run --rm \
  --env-file "$ENV_FILE" \
  -v "${SSH_KEY_FILE}:/run/secrets/id_ed25519:ro" \
  -p "${API_PORT}:${API_PORT}" \
  "$IMAGE" \
  start
