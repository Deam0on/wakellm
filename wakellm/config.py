import os
import re
import stat
import sys

import yaml

# ---------------------------------------------------------------------------
# Valid pod ID: lowercase alphanumeric + hyphens, 8-20 characters.
# Guards against f-string injection into GraphQL mutations.
# ---------------------------------------------------------------------------
_POD_ID_RE = re.compile(r'^[a-z0-9][a-z0-9\-]{6,18}[a-z0-9]$')

REQUIRED_CONFIG_KEYS = {
    'runpod': ['api_key', 'pod_id'],
    'ssh': ['key_path'],
    'ports': None,  # must be a non-empty list
}

# Path used when WAKELLM_SSH_KEY (raw key content) is provided via env.
_ENV_SSH_KEY_TMP = "/tmp/wakellm_ssh_key"


def _write_ssh_key_from_env(key_content: str) -> str:
    """
    Write the raw SSH private key content to a temp file with 0600 permissions.
    Returns the path to the written file.
    """
    with open(_ENV_SSH_KEY_TMP, "w") as f:
        f.write(key_content)
        if not key_content.endswith("\n"):
            f.write("\n")
    os.chmod(_ENV_SSH_KEY_TMP, stat.S_IRUSR | stat.S_IWUSR)
    return _ENV_SSH_KEY_TMP


def load_config_from_env() -> dict:
    """
    Build the config dict entirely from environment variables.
    Raises EnvironmentError listing any missing required variables.

    Required env vars:
        WAKELLM_RUNPOD_API_KEY
        WAKELLM_RUNPOD_POD_ID
        WAKELLM_SSH_KEY_PATH  or  WAKELLM_SSH_KEY  (raw key content — written to /tmp)
        WAKELLM_PORTS         comma-separated, e.g. "11434:11434,8080:8080"
    """
    missing = []
    for var in ("WAKELLM_RUNPOD_API_KEY", "WAKELLM_RUNPOD_POD_ID", "WAKELLM_PORTS"):
        if not os.environ.get(var):
            missing.append(var)
    if not os.environ.get("WAKELLM_SSH_KEY_PATH") and not os.environ.get("WAKELLM_SSH_KEY"):
        missing.append("WAKELLM_SSH_KEY_PATH or WAKELLM_SSH_KEY")
    if missing:
        raise EnvironmentError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    if os.environ.get("WAKELLM_SSH_KEY"):
        ssh_key_path = _write_ssh_key_from_env(os.environ["WAKELLM_SSH_KEY"])
    else:
        ssh_key_path = os.environ["WAKELLM_SSH_KEY_PATH"]

    ports = [p.strip() for p in os.environ["WAKELLM_PORTS"].split(",") if p.strip()]

    def _env_int(var, default):
        val = os.environ.get(var)
        return int(val) if val is not None else default

    def _env_bool(var, default):
        val = os.environ.get(var)
        if val is None:
            return default
        return val.lower() not in ("0", "false", "no")

    return {
        "runpod": {
            "api_key": os.environ["WAKELLM_RUNPOD_API_KEY"],
            "pod_id":  os.environ["WAKELLM_RUNPOD_POD_ID"],
        },
        "ssh": {
            "key_path": ssh_key_path,
        },
        "ports": ports,
        "startup": {
            "pod_start_timeout_minutes": _env_int("WAKELLM_STARTUP_TIMEOUT", 5),
            "ssh_boot_wait_seconds":     _env_int("WAKELLM_STARTUP_BOOT_WAIT", 10),
        },
        "autokill": {
            "idle_timeout_minutes":        _env_int("WAKELLM_AUTOKILL_IDLE", 15),
            "hard_timeout_minutes":        _env_int("WAKELLM_AUTOKILL_HARD", 120),
            "ollama_poll_interval_seconds": _env_int("WAKELLM_AUTOKILL_POLL", 30),
            "ollama_remote_port":          _env_int("WAKELLM_AUTOKILL_OLLAMA_PORT", 11434),
        },
        "api": {
            "enabled": _env_bool("WAKELLM_API_ENABLED", True),
            "host":    os.environ.get("WAKELLM_API_HOST", "127.0.0.1"),
            "port":    _env_int("WAKELLM_API_PORT", 8765),
        },
    }


def load_config(path):
    # If the primary required env var is present, skip the YAML file entirely.
    if os.environ.get("WAKELLM_RUNPOD_API_KEY"):
        try:
            return load_config_from_env()
        except EnvironmentError as e:
            print(f"[ERROR] Environment config error: {e}")
            sys.exit(1)

    try:
        with open(path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"[ERROR] {path} not found. Please copy config.example.yaml to config.yaml")
        sys.exit(1)


def validate_config(config):
    errors = []
    for section, keys in REQUIRED_CONFIG_KEYS.items():
        if section not in config:
            errors.append(f"Missing section '{section}'")
            continue
        if keys is None:
            if not isinstance(config[section], list) or len(config[section]) == 0:
                errors.append(f"'{section}' must be a non-empty list")
        else:
            for key in keys:
                if not config[section].get(key):
                    errors.append(f"Missing or empty '{section}.{key}'")
    if errors:
        for e in errors:
            print(f"[ERROR] Config error: {e}")
        sys.exit(1)


def validate_pod_id(pod_id):
    if not _POD_ID_RE.match(pod_id):
        print(f"[ERROR] Invalid pod_id format: '{pod_id}'. "
              "Expected lowercase alphanumeric with hyphens, 8-20 characters.")
        sys.exit(1)


def cfg(config, section, key, default):
    """Generic config section accessor with a default fallback."""
    return config.get(section, {}).get(key, default)


def ollama_local_port(config):
    """Return the local port mapped to the remote Ollama port, or None."""
    ollama_remote = cfg(config, 'autokill', 'ollama_remote_port', 11434)
    for port_map in config['ports']:
        local_p, remote_p = port_map.split(':')
        if int(remote_p) == ollama_remote:
            return int(local_p)
    return None
