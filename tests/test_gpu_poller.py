import platform
import time
from unittest.mock import MagicMock, patch

import pytest

from shared_state import SharedState
from gpu_poller import GpuPoller

windows_only = pytest.mark.skipif(
    platform.system() != "Windows", reason="Windows-only WMI GPU backend"
)


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


@windows_only
def test_query_sums_3d_engines():
    entries = [
        _make_entry("pid_123_luid_0_phys_0_eng_0_engtype_3D", 30),
        _make_entry("pid_456_luid_0_phys_0_eng_1_engtype_3D", 25),
        _make_entry("pid_789_luid_0_phys_0_eng_0_engtype_VideoDecode", 10),
    ]
    with _mock_wmi(entries):
        result = GpuPoller(SharedState())._query_gpu_3d()
    assert result == 55.0  # 30+25 only; VideoDecode excluded


@windows_only
def test_query_ignores_non_3d_engines():
    entries = [
        _make_entry("pid_1_luid_0_phys_0_eng_0_engtype_Copy", 50),
        _make_entry("pid_2_luid_0_phys_0_eng_0_engtype_VideoDecode", 40),
    ]
    with _mock_wmi(entries):
        result = GpuPoller(SharedState())._query_gpu_3d()
    assert result == 0.0


@windows_only
def test_query_caps_at_100():
    entries = [
        _make_entry("pid_1_luid_0_phys_0_eng_0_engtype_3D", 80),
        _make_entry("pid_2_luid_0_phys_0_eng_0_engtype_3D", 60),
    ]
    with _mock_wmi(entries):
        result = GpuPoller(SharedState())._query_gpu_3d()
    assert result == 100.0


@windows_only
def test_query_returns_zero_on_exception():
    with patch("gpu_poller.wmi.WMI", side_effect=Exception("WMI unavailable")):
        result = GpuPoller(SharedState())._query_gpu_3d()
    assert result == 0.0


@windows_only
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
    with patch.object(GpuPoller, "_query_gpu_3d_linux", return_value=0.0), \
         patch("gpu_poller.IS_WINDOWS", False):
        poller = GpuPoller(state, interval=0.05)
        poller.start()
        time.sleep(0.1)
        poller.stop()
        poller.join(timeout=1.0)
    assert not poller.is_alive()


def _mock_subprocess_run(stdout: str, returncode: int = 0):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    return result


def test_nvidia_smi_reports_max_utilization_across_gpus():
    with patch("gpu_poller.subprocess.run", return_value=_mock_subprocess_run("12\n47\n")):
        result = GpuPoller(SharedState())._query_nvidia_smi()
    assert result == 47.0


def test_nvidia_smi_returns_none_on_missing_binary():
    with patch("gpu_poller.subprocess.run", side_effect=FileNotFoundError()):
        result = GpuPoller(SharedState())._query_nvidia_smi()
    assert result is None


def test_nvidia_smi_returns_none_on_nonzero_exit():
    with patch("gpu_poller.subprocess.run", return_value=_mock_subprocess_run("", returncode=1)):
        result = GpuPoller(SharedState())._query_nvidia_smi()
    assert result is None


def test_nvidia_smi_caps_at_100():
    with patch("gpu_poller.subprocess.run", return_value=_mock_subprocess_run("150\n")):
        result = GpuPoller(SharedState())._query_nvidia_smi()
    assert result == 100.0


def test_amdgpu_sysfs_reads_busy_percent(tmp_path):
    fake_path = tmp_path / "gpu_busy_percent"
    fake_path.write_text("33\n")
    with patch("gpu_poller.glob.glob", return_value=[str(fake_path)]):
        result = GpuPoller(SharedState())._query_amdgpu_sysfs()
    assert result == 33.0


def test_amdgpu_sysfs_returns_none_when_absent():
    with patch("gpu_poller.glob.glob", return_value=[]):
        result = GpuPoller(SharedState())._query_amdgpu_sysfs()
    assert result is None


def test_linux_query_falls_back_from_nvidia_to_amd():
    poller = GpuPoller(SharedState())
    with patch.object(poller, "_query_nvidia_smi", return_value=None), \
         patch.object(poller, "_query_amdgpu_sysfs", return_value=22.0):
        assert poller._query_gpu_3d_linux() == 22.0


def test_linux_query_defaults_to_zero_when_no_gpu_data():
    poller = GpuPoller(SharedState())
    with patch.object(poller, "_query_nvidia_smi", return_value=None), \
         patch.object(poller, "_query_amdgpu_sysfs", return_value=None):
        assert poller._query_gpu_3d_linux() == 0.0
