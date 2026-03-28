import time
from unittest.mock import patch
from shared_state import SharedState
from cpu_poller import CpuPoller


def test_poller_updates_shared_state():
    state = SharedState()
    poller = CpuPoller(state, interval=0.05)

    with patch("cpu_poller.psutil.cpu_percent", return_value=42.0):
        poller.start()
        time.sleep(0.15)  # allow 2-3 polls
        poller.stop()
        poller.join(timeout=1.0)

    assert state.get_cpu() == 42.0


def test_poller_stops_cleanly():
    state = SharedState()
    poller = CpuPoller(state, interval=0.05)
    poller.start()
    time.sleep(0.1)
    poller.stop()
    poller.join(timeout=1.0)
    assert not poller.is_alive()
