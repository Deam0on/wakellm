import time

import requests

from .config import cfg, ollama_local_port


def run_tunnel_monitor(stop_event, get_tunnel_proc, shutdown_cb):
    """
    Daemon thread target: polls the SSH tunnel subprocess every 5 seconds.
    If the process has exited while we are still meant to be running,
    calls shutdown_cb() to trigger a fail-safe shutdown.

    Args:
        stop_event:       threading.Event — set when shutdown is initiated.
        get_tunnel_proc:  callable () -> Popen | None
        shutdown_cb:      callable () -> None
    """
    while not stop_event.wait(timeout=5):
        proc = get_tunnel_proc()
        if proc and proc.poll() is not None:
            print("\n[ERROR] SSH tunnel process died unexpectedly. "
                  "Initiating emergency shutdown to prevent runaway billing...")
            shutdown_cb()
            return


def run_idle_monitor(config, stop_event, get_start_time, set_last_active, shutdown_cb):
    """
    Daemon thread target: polls Ollama /api/ps and enforces the hard uptime cap.

    Idle logic:
      - If Ollama reports no loaded models for > idle_timeout_minutes → shutdown.
      - If total uptime exceeds hard_timeout_minutes → shutdown regardless.
      - If Ollama is unreachable (still booting), do NOT start the idle clock.

    Args:
        config:           Full config dict.
        stop_event:       threading.Event — set when shutdown is initiated.
        get_start_time:   callable () -> float | None  (monotonic start time)
        set_last_active:  callable (float) -> None     (monotonic time of last activity)
        shutdown_cb:      callable () -> None
    """
    idle_timeout_s  = cfg(config, 'autokill', 'idle_timeout_minutes', 15) * 60
    hard_timeout_s  = cfg(config, 'autokill', 'hard_timeout_minutes', 120) * 60
    poll_interval_s = cfg(config, 'autokill', 'ollama_poll_interval_seconds', 30)
    ol_port         = ollama_local_port(config)

    if ol_port is None:
        print("[WARN] Auto-kill: no port mapping found for Ollama remote port. "
              "Idle monitor disabled; hard timeout still enforced.")

    idle_since = None

    while not stop_event.wait(timeout=poll_interval_s):
        now = time.monotonic()

        # --- Hard timeout ---
        start_time = get_start_time()
        if start_time and (now - start_time) >= hard_timeout_s:
            print(f"\n[INFO] Hard timeout of "
                  f"{cfg(config, 'autokill', 'hard_timeout_minutes', 120)} "
                  f"minute(s) reached. Shutting down...")
            shutdown_cb()
            return

        if ol_port is None:
            continue

        # --- Ollama idle check ---
        try:
            resp = requests.get(f"http://localhost:{ol_port}/api/ps", timeout=5)
            resp.raise_for_status()
            models = resp.json().get('models', [])

            if models:
                idle_since = None
                set_last_active(now)
            else:
                if idle_since is None:
                    idle_since = now
                idle_duration = now - idle_since
                remaining     = idle_timeout_s - idle_duration
                print(f"[INFO] Ollama idle for {idle_duration / 60:.1f} min "
                      f"(auto-kill in {remaining / 60:.1f} min)...")

                if idle_duration >= idle_timeout_s:
                    print(f"\n[INFO] Idle timeout of "
                          f"{cfg(config, 'autokill', 'idle_timeout_minutes', 15)} "
                          f"minute(s) reached. Shutting down...")
                    shutdown_cb()
                    return

        except requests.exceptions.ConnectionError:
            # Ollama not yet reachable (still booting) — do not start idle clock
            print("[INFO] Auto-kill: Ollama not yet reachable, skipping idle check...")
        except Exception as e:
            print(f"[WARN] Auto-kill: unexpected error polling Ollama: {e}")
