#!/usr/bin/env bash
# WakeLLM container entrypoint.
# Dispatches start/stop/status to the wakellm CLI, or exec's an arbitrary
# command (e.g. python3 -m pytest ...) when called directly.
# The build/test/scan pipeline lives in start-wake.sh on the host.
set -euo pipefail

case "${1:-}" in
  start|stop|status|"")
    exec python3 -m wakellm "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
