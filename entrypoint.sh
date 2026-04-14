#!/usr/bin/env bash
# WakeLLM container entrypoint.
# Runs unit tests and Trivy security scans before starting the application.
# Any failure aborts startup — no broken or vulnerable code runs.
set -euo pipefail

echo "========================================"
echo " WakeLLM Container Startup Gate"
echo "========================================"

# ---------------------------------------------------------------------------
# 1. Unit tests
# ---------------------------------------------------------------------------
echo ""
echo "[1/3] Running unit tests..."
python3 -m pytest tests/ -v --tb=short
echo "[PASS] All tests passed."

# ---------------------------------------------------------------------------
# 2. Trivy: dependency / filesystem scan (requirements.txt + installed packages)
# ---------------------------------------------------------------------------
echo ""
echo "[2/3] Trivy: scanning installed Python packages..."
trivy fs \
  --scanners vuln \
  --severity CRITICAL \
  --exit-code 1 \
  --no-progress \
  /app
echo "[PASS] No CRITICAL vulnerabilities in installed packages."

# ---------------------------------------------------------------------------
# 3. Trivy: full rootfs scan (OS packages, system libraries)
#    --skip-files excludes the Trivy binary itself from its own scan; the
#    binary is a build/scanning tool and is not reachable at application runtime.
# ---------------------------------------------------------------------------
echo ""
echo "[3/3] Trivy: scanning full container filesystem..."
trivy rootfs \
  --scanners vuln \
  --severity CRITICAL \
  --exit-code 1 \
  --no-progress \
  --skip-files /usr/bin/trivy \
  /
echo "[PASS] No CRITICAL vulnerabilities in container OS."

# ---------------------------------------------------------------------------
# Start WakeLLM
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " All checks passed — starting WakeLLM"
echo "========================================"
echo ""
exec python3 -m wakellm "$@"
