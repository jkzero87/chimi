"""Process management for the chimi llama-server.

Only one llama-server can be resident at a time (16GB card). The server may
also have been started by hand outside this module (as happened during
certification — see PROJECT_TRUTH.md) so every function here checks the
actual OS state bound to PORT rather than trusting in-memory or on-disk
bookkeeping alone.
"""
import os
import re
import signal
import subprocess
import time
import urllib.error
import urllib.request

from config import PORT
from agent.profiles import PROFILES

STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".server_state")
HEALTH_URL = f"http://127.0.0.1:{PORT}/health"
START_TIMEOUT_S = 180
STOP_TIMEOUT_S = 20
POLL_INTERVAL_S = 1.0


def _bound_pid():
    """PID of whatever process is listening on PORT, or None if nothing is."""
    out = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True, timeout=10).stdout
    for line in out.splitlines():
        fields = line.split()
        if len(fields) < 4 or fields[0] != "LISTEN":
            continue
        if not fields[3].endswith(f":{PORT}"):
            continue
        m = re.search(r"pid=(\d+)", line)
        if m:
            return int(m.group(1))
    return None


def _health_ok():
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _read_state():
    if not os.path.exists(STATE_FILE):
        return None
    try:
        pid_str, profile = open(STATE_FILE).read().strip().split("\n", 1)
        return int(pid_str), profile
    except (ValueError, OSError):
        return None


def _write_state(pid, profile):
    with open(STATE_FILE, "w") as f:
        f.write(f"{pid}\n{profile}")


def _clear_state():
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)


def current_profile():
    """Name of the profile running on PORT, "unknown" if something else is
    bound there, or None if nothing is listening."""
    pid = _bound_pid()
    if pid is None:
        return None
    state = _read_state()
    if state and state[0] == pid:
        return state[1]
    return "unknown"


def start(profile_name):
    if profile_name not in PROFILES:
        raise ValueError(f"unknown profile: {profile_name}")
    cmd = PROFILES[profile_name] + ["--host", "127.0.0.1", "--port", str(PORT)]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _write_state(proc.pid, profile_name)
    deadline = time.time() + START_TIMEOUT_S
    while time.time() < deadline:
        if proc.poll() is not None:
            _clear_state()
            raise RuntimeError(
                f"llama-server exited early (code {proc.returncode}) while starting profile '{profile_name}'"
            )
        if _health_ok():
            return
        time.sleep(POLL_INTERVAL_S)
    _clear_state()
    raise TimeoutError(f"llama-server did not become healthy within {START_TIMEOUT_S}s (profile '{profile_name}')")


def stop():
    """Terminate whatever is bound to PORT, ours or not, and wait for the
    port to free."""
    pid = _bound_pid()
    if pid is None:
        _clear_state()
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _clear_state()
        return
    deadline = time.time() + STOP_TIMEOUT_S
    while time.time() < deadline:
        if _bound_pid() is None:
            _clear_state()
            return
        time.sleep(POLL_INTERVAL_S)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        _clear_state()
        return
    deadline = time.time() + STOP_TIMEOUT_S
    while time.time() < deadline:
        if _bound_pid() is None:
            _clear_state()
            return
        time.sleep(POLL_INTERVAL_S)
    raise RuntimeError(f"port {PORT} still bound after SIGKILL to pid {pid}")


def ensure(profile_name):
    """No-op if profile_name is already running (and known to be ours).
    Otherwise stop whatever is on PORT -- ours, unknown, or absent -- and
    start profile_name."""
    if current_profile() == profile_name:
        return
    stop()
    start(profile_name)
