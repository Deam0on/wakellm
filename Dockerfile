# ============================================================
# WakeLLM — container image
# Base: python:3.12-slim (Debian slim)
#
# On every container start, entrypoint.sh gates startup with:
#   1. pytest unit tests
#   2. trivy fs scan (Python packages)
#   3. trivy rootfs scan (full OS)
# Only on full pass does WakeLLM start.
# ============================================================
FROM python:3.12-slim

# ---------------------------------------------------------------------------
# System dependencies
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    curl \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Install Trivy via the official Aqua Security apt repository.
# This always resolves the latest stable release without pinning a version.
# ---------------------------------------------------------------------------
RUN set -eux; \
    curl -sfL https://aquasecurity.github.io/trivy-repo/deb/public.key \
        | gpg --dearmor > /usr/share/keyrings/trivy.gpg; \
    echo "deb [signed-by=/usr/share/keyrings/trivy.gpg] https://aquasecurity.github.io/trivy-repo/deb generic main" \
        > /etc/apt/sources.list.d/trivy.list; \
    apt-get update && apt-get install -y --no-install-recommends trivy; \
    rm -rf /var/lib/apt/lists/*; \
    trivy --version

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
WORKDIR /app

# Install Python dependencies first (layer-cached unless requirements change)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application package and tests
COPY wakellm/ ./wakellm/
COPY wakellm.py ./
COPY tests/ ./tests/

# Trivy DB cache directory (pre-warm at build time for faster startups)
RUN trivy --cache-dir /var/cache/trivy image --download-db-only --no-progress 2>/dev/null || true

# Entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ---------------------------------------------------------------------------
# Runtime
# No config.yaml in the image — provide via environment variables:
#   WAKELLM_RUNPOD_API_KEY, WAKELLM_RUNPOD_POD_ID,
#   WAKELLM_SSH_KEY or WAKELLM_SSH_KEY_PATH (bind-mount),
#   WAKELLM_PORTS  (comma-separated, e.g. "11434:11434,8080:8080")
# ---------------------------------------------------------------------------
ENTRYPOINT ["/entrypoint.sh"]
CMD ["start"]
