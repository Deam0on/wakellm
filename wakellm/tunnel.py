import os
import subprocess


def start_tunnel(config, pod_info):
    """
    Build and launch the SSH port-forwarding subprocess.

    Returns the running Popen object.
    Raises RuntimeError if the SSH endpoint cannot be located in pod_info.
    """
    ssh_ip   = None
    ssh_port = None
    for port in pod_info['runtime']['ports']:
        if port['privatePort'] == 22 and port['type'] == 'tcp':
            ssh_ip   = port['ip']
            ssh_port = port['publicPort']
            break

    if not ssh_ip or not ssh_port:
        raise RuntimeError("Could not find SSH port mapping in RunPod response.")

    print(f"[INFO] Establishing SSH tunnel to {ssh_ip}:{ssh_port}...")

    ssh_cmd = [
        "ssh", "-i", os.path.expanduser(config['ssh']['key_path']),
        "-N",                          # no remote command — port-forward only
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-p", str(ssh_port),
        f"root@{ssh_ip}",
    ]

    for port_map in config['ports']:
        local_p, remote_p = port_map.split(':')
        ssh_cmd.extend(["-L", f"{local_p}:localhost:{remote_p}"])
        print(f"   -> Forwarding local port {local_p} to remote {remote_p}")

    proc = subprocess.Popen(ssh_cmd)
    print("\n[INFO] WakeLLM bridge is active. Press Ctrl+C to terminate and stop the pod.")
    return proc
