import time
from unittest.mock import MagicMock, patch

from shared_state import SharedState
from gpu_poller import GpuPoller


def _make_entry(name: str, utilization: int) -> MagicMock:
    e = MagicMock()
    e.Name = name
    e.UtilizationPercentage = str(utilization)
    return e


def _mock_wmi(entries):
    """Return a context-manager-friendly patch for gpu_poller.wmi.WMI."""
    instance = MagicMock()
    instance.Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine.return_value = entries
    return patch("gpu_poller.wmi.WMI", return_value=instance)


def test_query_sums_3d_engines():
    entries = [
        _make_entry("pid_123_luid_0_phys_0_eng_0_engtype_3D", 30),
        _make_entry("pid_456_luid_0_phys_0_eng_1_engtype_3D", 25),
        _make_entry("pid_789_luid_0_phys_0_eng_0_engtype_VideoDecode", 10),
    ]
    with _mock_wmi(entries):
        result = GpuPoller(SharedState())._query_gpu_3d()
    assert result == 55.0  # 30+25 only; VideoDecode excluded


def test_query_ignores_non_3d_engines():
    entries = [
        _make_entry("pid_1_luid_0_phys_0_eng_0_engtype_Copy", 50),
        _make_entry("pid_2_luid_0_phys_0_eng_0_engtype_VideoDecode", 40),
    ]
    with _mock_wmi(entries):
        result = GpuPoller(SharedState())._query_gpu_3d()
    assert result == 0.0


def test_query_caps_at_100():
    entries = [
        _make_entry("pid_1_luid_0_phys_0_eng_0_engtype_3D", 80),
        _make_entry("pid_2_luid_0_phys_0_eng_0_engtype_3D", 60),
    ]
    with _mock_wmi(entries):
        result = GpuPoller(SharedState())._query_gpu_3d()
    assert result == 100.0


def test_query_returns_zero_on_exception():
    with patch("gpu_poller.wmi.WMI", side_effect=Exception("WMI unavailable")):
        result = GpuPoller(SharedState())._query_gpu_3d()
    assert result == 0.0


def test_poller_updates_shared_state():
    state = SharedState()
    entries = [_make_entry("pid_1_luid_0_phys_0_eng_0_engtype_3D", 65)]
    with _mock_wmi(entries):
        poller = GpuPoller(state, interval=0.05)
        poller.start()
        time.sleep(0.15)
        poller.stop()
        poller.join(timeout=1.0)
    assert state.get_gpu_3d_percent() == 65.0


def test_poller_stops_cleanly():
    state = SharedState()
    with _mock_wmi([]):
        poller = GpuPoller(state, interval=0.05)
        poller.start()
        time.sleep(0.1)
        poller.stop()
        poller.join(timeout=1.0)
    assert not poller.is_alive()
