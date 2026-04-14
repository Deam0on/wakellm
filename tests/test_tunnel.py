"""Tests for wakellm/tunnel.py"""
import subprocess

import pytest

from wakellm.tunnel import start_tunnel


class TestStartTunnel:
    def test_happy_path_returns_popen(self, minimal_config, mock_pod_info, mocker):
        mock_proc = mocker.MagicMock(spec=subprocess.Popen)
        mocker.patch("subprocess.Popen", return_value=mock_proc)
        result = start_tunnel(minimal_config, mock_pod_info)
        assert result is mock_proc

    def test_ssh_command_structure(self, minimal_config, mock_pod_info, mocker):
        mock_popen = mocker.patch("subprocess.Popen")
        start_tunnel(minimal_config, mock_pod_info)
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "ssh"
        assert "-N" in cmd
        assert "-i" in cmd

    def test_strict_host_key_checking_disabled(self, minimal_config, mock_pod_info, mocker):
        mock_popen = mocker.patch("subprocess.Popen")
        start_tunnel(minimal_config, mock_pod_info)
        cmd = mock_popen.call_args[0][0]
        assert "StrictHostKeyChecking=no" in cmd
        assert "UserKnownHostsFile=/dev/null" in cmd

    def test_correct_ssh_host_and_port(self, minimal_config, mock_pod_info, mocker):
        mock_popen = mocker.patch("subprocess.Popen")
        start_tunnel(minimal_config, mock_pod_info)
        cmd = mock_popen.call_args[0][0]
        # Port comes after -p flag
        p_idx = cmd.index("-p")
        assert cmd[p_idx + 1] == "43210"
        assert "root@192.0.2.10" in cmd

    def test_port_forwarding_flags(self, minimal_config, mock_pod_info, mocker):
        mock_popen = mocker.patch("subprocess.Popen")
        start_tunnel(minimal_config, mock_pod_info)
        cmd = mock_popen.call_args[0][0]
        # Both port mappings from minimal_config should appear as -L entries
        l_entries = [cmd[i + 1] for i, v in enumerate(cmd) if v == "-L"]
        assert "11434:localhost:11434" in l_entries
        assert "8080:localhost:8080" in l_entries

    def test_key_path_expanded(self, minimal_config, mock_pod_info, mocker):
        minimal_config["ssh"]["key_path"] = "~/.ssh/id_ed25519"
        mock_popen = mocker.patch("subprocess.Popen")
        mocker.patch("os.path.expanduser", return_value="/home/user/.ssh/id_ed25519")
        start_tunnel(minimal_config, mock_pod_info)
        cmd = mock_popen.call_args[0][0]
        i_idx = cmd.index("-i")
        assert cmd[i_idx + 1] == "/home/user/.ssh/id_ed25519"

    def test_missing_ssh_port_raises_runtime_error(self, minimal_config, mocker):
        mocker.patch("subprocess.Popen")
        pod_info_no_ssh = {
            "id": "abc123def456",
            "desiredStatus": "RUNNING",
            "runtime": {
                "ports": [
                    {"ip": "192.0.2.10", "isIpPublic": True,
                     "privatePort": 8080, "publicPort": 8080, "type": "http"},
                ]
            },
        }
        with pytest.raises(RuntimeError, match="Could not find SSH port mapping"):
            start_tunnel(minimal_config, pod_info_no_ssh)
