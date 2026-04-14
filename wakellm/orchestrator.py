import subprocess
import threading
import time

from .config import load_config, validate_config, validate_pod_id, cfg
from .runpod import RunPodClient
from .tunnel import start_tunnel
from .monitors import run_tunnel_monitor, run_idle_monitor
from .api import start_api_server as _start_api_server


class WakeLLM:
    STATE_STOPPED  = "stopped"
    STATE_STARTING = "starting"
    STATE_RUNNING  = "running"
    STATE_STOPPING = "stopping"

    def __init__(self, config_path="config.yaml"):
        self.config = load_config(config_path)
        validate_config(self.config)
        validate_pod_id(self.config['runpod']['pod_id'])

        self.pod_id  = self.config['runpod']['pod_id']
        self._runpod = RunPodClient(self.config)

        self.tunnel_process = None

        self._state      = self.STATE_STOPPED
        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()

        self._start_time       = None
        self._last_active_time = None

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _set_state(self, state):
        with self._state_lock:
            self._state = state

    def get_state(self):
        with self._state_lock:
            return self._state

    # ------------------------------------------------------------------
    # Pod operations (delegate to RunPodClient)
    # ------------------------------------------------------------------

    def stop_pod(self):
        self._runpod.stop_pod()

    def get_pod_info(self):
        return self._runpod.get_pod_info()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_lifecycle(self):
        """
        Provision pod → SSH boot wait → tunnel → start monitor threads.
        Thread-safe: returns False immediately if already starting or running.
        """
        with self._state_lock:
            if self._state in (self.STATE_STARTING, self.STATE_RUNNING):
                return False
            self._state = self.STATE_STARTING

        try:
            pod_info = self._runpod.start_pod()

            boot_wait = cfg(self.config, 'startup', 'ssh_boot_wait_seconds', 10)
            print(f"[INFO] Waiting {boot_wait}s for SSH daemon to start on the pod...")
            time.sleep(boot_wait)

            self.tunnel_process = start_tunnel(self.config, pod_info)

            self._stop_event.clear()
            self._start_time       = time.monotonic()
            self._last_active_time = self._start_time
            self._set_state(self.STATE_RUNNING)

            threading.Thread(
                target=run_tunnel_monitor,
                args=(self._stop_event, lambda: self.tunnel_process, self.shutdown),
                daemon=True,
                name="tunnel-monitor",
            ).start()

            threading.Thread(
                target=run_idle_monitor,
                args=(
                    self.config,
                    self._stop_event,
                    lambda: self._start_time,
                    lambda t: setattr(self, '_last_active_time', t),
                    self.shutdown,
                ),
                daemon=True,
                name="idle-monitor",
            ).start()

            return True

        except Exception as e:
            print(f"[ERROR] Lifecycle start failed: {e}")
            self.shutdown()
            return False

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self):
        """
        Idempotent. Signals monitor threads to stop, terminates the SSH
        tunnel, and sends the podStop mutation to RunPod.
        """
        with self._state_lock:
            if self._state == self.STATE_STOPPING:
                return
            self._state = self.STATE_STOPPING

        self._stop_event.set()  # unblocks all monitor threads

        if self.tunnel_process and self.tunnel_process.poll() is None:
            print("\n[INFO] Closing SSH tunnel...")
            self.tunnel_process.terminate()
            try:
                self.tunnel_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.tunnel_process.kill()

        self._runpod.stop_pod()
        self._set_state(self.STATE_STOPPED)

    # ------------------------------------------------------------------
    # API server
    # ------------------------------------------------------------------

    def start_api_server(self):
        _start_api_server(self, self.config)
