import argparse
import time
import requests
import yaml
import subprocess
import sys
import os

class WakeLLM:
    def __init__(self, config_path="config.yaml"):
        self.config = self._load_config(config_path)
        self.api_key = self.config['runpod']['api_key']
        self.pod_id = self.config['runpod']['pod_id']
        self.endpoint = f"https://api.runpod.io/graphql?api_key={self.api_key}"
        self.tunnel_process = None

    def _load_config(self, path):
        try:
            with open(path, 'r') as file:
                return yaml.safe_load(file)
        except FileNotFoundError:
            print(f"❌ Error: {path} not found. Please copy config.example.yaml to config.yaml")
            sys.exit(1)

    def _run_graphql(self, query):
        headers = {"Content-Type": "application/json"}
        response = requests.post(self.endpoint, json={"query": query}, headers=headers)
        response.raise_for_status()
        return response.json()

    def start_pod(self):
        print(f"🚀 Waking up Pod {self.pod_id}...")
        query = f'mutation {{ podResume(input: {{podId: "{self.pod_id}", gpuCount: 1}}) {{ id desiredStatus }} }}'
        self._run_graphql(query)
        
        # Poll until the pod is fully running and has an IP assigned
        while True:
            print("⏳ Waiting for pod to become ready...")
            time.sleep(5)
            pod_info = self.get_pod_info()
            if pod_info and pod_info.get("desiredStatus") == "RUNNING" and pod_info.get("runtime"):
                print("✅ Pod is awake!")
                return pod_info

    def stop_pod(self):
        print(f"\n🛑 Stopping Pod {self.pod_id} to halt billing...")
        query = f'mutation {{ podStop(input: {{podId: "{self.pod_id}"}}) {{ id desiredStatus }} }}'
        self._run_graphql(query)
        print("💤 Pod successfully sent to sleep.")

    def get_pod_info(self):
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

    def start_tunnel(self, pod_info):
        # Find the public SSH port and IP provided by RunPod
        ssh_ip = None
        ssh_port = None
        for port in pod_info['runtime']['ports']:
            if port['privatePort'] == 22 and port['type'] == 'tcp':
                ssh_ip = port['ip']
                ssh_port = port['publicPort']
                break

        if not ssh_ip or not ssh_port:
            print("❌ Error: Could not find SSH port mapping in RunPod response.")
            self.stop_pod()
            sys.exit(1)

        print(f"🔗 Establishing SSH Tunnel to {ssh_ip}:{ssh_port}...")
        
        # Build the SSH command with strict host key checking disabled for ephemeral IPs
        ssh_cmd = [
            "ssh", "-i", os.path.expanduser(self.config['ssh']['key_path']),
            "-N", # Do not execute a remote command (just forward ports)
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-p", str(ssh_port),
            f"root@{ssh_ip}"
        ]

        # Add the port mappings from config
        for port_map in self.config['ports']:
            local_p, remote_p = port_map.split(':')
            ssh_cmd.extend(["-L", f"{local_p}:localhost:{remote_p}"])
            print(f"   -> Forwarding local port {local_p} to remote {remote_p}")

        # Start the tunnel as a background subprocess
        self.tunnel_process = subprocess.Popen(ssh_cmd)
        print("\n✨ WakeLLM Bridge is active! Press Ctrl+C to terminate and stop the pod.")

    def shutdown(self):
        if self.tunnel_process:
            print("\n🔌 Closing SSH Tunnel...")
            self.tunnel_process.terminate()
            self.tunnel_process.wait()
        self.stop_pod()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WakeLLM Orchestrator")
    parser.add_argument("action", choices=["start", "stop"], help="Action to perform")
    args = parser.parse_args()

    engine = WakeLLM()

    if args.action == "start":
        try:
            info = engine.start_pod()
            # Give the container OS an extra 10 seconds to boot the SSH daemon
            time.sleep(10) 
            engine.start_tunnel(info)
            
            # Keep the main thread alive until user interrupts
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            engine.shutdown()
        except Exception as e:
            print(f"❌ An error occurred: {e}")
            engine.shutdown()
    
    elif args.action == "stop":
        engine.stop_pod()
