"""Tests for wakellm/runpod.py"""
import sys
import time
import unittest.mock as mock

import pytest
import requests

from wakellm.runpod import RunPodClient


@pytest.fixture
def client(minimal_config):
    return RunPodClient(minimal_config)


@pytest.fixture
def running_pod_response():
    return {
        "data": {
            "pod": {
                "id": "abc123def456",
                "desiredStatus": "RUNNING",
                "runtime": {
                    "ports": [
                        {"ip": "192.0.2.10", "isIpPublic": True,
                         "privatePort": 22, "publicPort": 43210, "type": "tcp"},
                    ]
                },
            }
        }
    }


@pytest.fixture
def stopped_pod_response():
    return {
        "data": {
            "pod": {
                "id": "abc123def456",
                "desiredStatus": "EXITED",
                "runtime": None,
            }
        }
    }


# ---------------------------------------------------------------------------
# _run_graphql
# ---------------------------------------------------------------------------

class TestRunGraphql:
    def test_success_returns_parsed_json(self, client, mocker):
        mock_resp = mocker.MagicMock()
        mock_resp.json.return_value = {"data": {"pod": {"id": "abc123def456"}}}
        mocker.patch("requests.post", return_value=mock_resp)
        result = client._run_graphql("query { pod }")
        assert result["data"]["pod"]["id"] == "abc123def456"

    def test_http_error_raises(self, client, mocker):
        mock_resp = mocker.MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("401")
        mocker.patch("requests.post", return_value=mock_resp)
        with pytest.raises(requests.HTTPError):
            client._run_graphql("query { pod }")


# ---------------------------------------------------------------------------
# start_pod
# ---------------------------------------------------------------------------

class TestStartPod:
    def test_happy_path_returns_pod_info(self, client, mocker, running_pod_response):
        mocker.patch("requests.post", return_value=mocker.MagicMock(
            json=mocker.MagicMock(return_value=running_pod_response)
        ))
        mocker.patch("time.sleep")
        result = client.start_pod()
        assert result["desiredStatus"] == "RUNNING"
        assert result["runtime"] is not None

    def test_timeout_calls_stop_and_exits(self, client, mocker, stopped_pod_response):
        mocker.patch("requests.post", return_value=mocker.MagicMock(
            json=mocker.MagicMock(return_value=stopped_pod_response)
        ))
        mocker.patch("time.sleep")
        # Set deadline to already-passed by making monotonic advance past the timeout
        start = time.monotonic()
        mocker.patch("time.monotonic", side_effect=[
            start,          # initial deadline calculation
            start + 999,    # first deadline check — already expired
        ])
        with pytest.raises(SystemExit) as exc:
            client.start_pod()
        assert exc.value.code == 1

    def test_polls_until_running(self, client, mocker, running_pod_response, stopped_pod_response):
        """Returns EXITED twice, then RUNNING on the third poll."""
        responses = [
            stopped_pod_response,
            stopped_pod_response,
            running_pod_response,
        ]
        call_count = {"n": 0}

        def fake_post(*args, **kwargs):
            resp = mocker.MagicMock()
            resp.json.return_value = responses[min(call_count["n"], len(responses) - 1)]
            call_count["n"] += 1
            return resp

        mocker.patch("requests.post", side_effect=fake_post)
        mocker.patch("time.sleep")
        result = client.start_pod()
        assert result["desiredStatus"] == "RUNNING"


# ---------------------------------------------------------------------------
# stop_pod
# ---------------------------------------------------------------------------

class TestStopPod:
    def test_happy_path_no_exception(self, client, mocker):
        mock_resp = mocker.MagicMock()
        mock_resp.json.return_value = {"data": {"podStop": {"id": "abc123def456", "desiredStatus": "EXITED"}}}
        mocker.patch("requests.post", return_value=mock_resp)
        client.stop_pod()  # must not raise

    def test_api_failure_swallowed(self, client, mocker):
        mock_resp = mocker.MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
        mocker.patch("requests.post", return_value=mock_resp)
        client.stop_pod()  # must not raise


# ---------------------------------------------------------------------------
# get_pod_info
# ---------------------------------------------------------------------------

class TestGetPodInfo:
    def test_returns_pod_dict(self, client, mocker, running_pod_response):
        mocker.patch("requests.post", return_value=mocker.MagicMock(
            json=mocker.MagicMock(return_value=running_pod_response)
        ))
        result = client.get_pod_info()
        assert result["id"] == "abc123def456"
        assert result["desiredStatus"] == "RUNNING"

    def test_returns_none_on_missing_data(self, client, mocker):
        mocker.patch("requests.post", return_value=mocker.MagicMock(
            json=mocker.MagicMock(return_value={"data": {}})
        ))
        assert client.get_pod_info() is None
