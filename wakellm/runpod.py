import sys
import time

import requests

from .config import cfg


class RunPodClient:
    """Handles all RunPod GraphQL API interactions."""

    def __init__(self, config):
        self.config   = config
        self.api_key  = config['runpod']['api_key']
        self.pod_id   = config['runpod']['pod_id']
        self.endpoint = f"https://api.runpod.io/graphql?api_key={self.api_key}"

    def _run_graphql(self, query):
        headers  = {"Content-Type": "application/json"}
        response = requests.post(self.endpoint, json={"query": query}, headers=headers)
        response.raise_for_status()
        return response.json()

    def start_pod(self):
        """Send the podResume mutation, then poll until RUNNING. Returns pod_info dict."""
        print(f"[INFO] Waking up pod {self.pod_id}...")
        query = (
            f'mutation {{ podResume(input: {{podId: "{self.pod_id}", gpuCount: 1}}) '
            f'{{ id desiredStatus }} }}'
        )
        self._run_graphql(query)

        timeout_minutes = cfg(self.config, 'startup', 'pod_start_timeout_minutes', 5)
        deadline        = time.monotonic() + timeout_minutes * 60
        poll_interval   = 5

        while True:
            if time.monotonic() > deadline:
                print(f"[ERROR] Pod did not become ready within {timeout_minutes} minute(s). "
                      "Stopping pod to prevent billing...")
                self.stop_pod()
                sys.exit(1)

            print("[INFO] Waiting for pod to become ready...")
            time.sleep(poll_interval)

            pod_info = self.get_pod_info()
            if pod_info and pod_info.get("desiredStatus") == "RUNNING" and pod_info.get("runtime"):
                print("[INFO] Pod is ready.")
                return pod_info

    def stop_pod(self):
        """Send the podStop mutation. Always attempts the call; logs rather than raising."""
        print(f"\n[INFO] Stopping pod {self.pod_id} to halt billing...")
        query = (
            f'mutation {{ podStop(input: {{podId: "{self.pod_id}"}}) '
            f'{{ id desiredStatus }} }}'
        )
        try:
            self._run_graphql(query)
            print("[INFO] Pod stopped.")
        except Exception as e:
            print(f"[WARN] stop_pod API call failed: {e}. "
                  "Please verify the pod is stopped manually in the RunPod dashboard.")

    def get_pod_info(self):
        """Query current pod state. Returns the pod dict or None."""
        query = f'''
        query Pod {{
          pod(input: {{podId: "{self.pod_id}"}}) {{
            id
            desiredStatus
            runtime {{
              ports {{ ip isIpPublic privatePort publicPort type }}
            }}
          }}
        }}
        '''
        res = self._run_graphql(query)
        return res.get('data', {}).get('pod')
