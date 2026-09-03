import glob
import platform
import subprocess
import threading

from shared_state import SharedState

IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    import pythoncom
    import wmi


class GpuPoller(threading.Thread):
    def __init__(self, state: SharedState, interval: float = 0.5):
        super().__init__(daemon=True)
        self._state = state
        self._interval = interval
        self._stop_event = threading.Event()

    def _query_gpu_3d(self, w) -> float:
        """Return total GPU 3D engine utilization % via Windows Performance Counters."""
        entries = w.Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine()
        total = sum(
            int(e.UtilizationPercentage)
            for e in entries
            if "engtype_3D" in e.Name
        )
        return min(float(total), 100.0)

    def _query_nvidia_smi(self):
        """Return GPU utilization % via nvidia-smi, or None if unavailable."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2.0,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        values = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                values.append(float(line))
            except ValueError:
                continue
        if not values:
            return None
        return min(max(values), 100.0)

    def _query_amdgpu_sysfs(self):
        """Return GPU utilization % via amdgpu's gpu_busy_percent sysfs file, or None."""
        values = []
        for path in glob.glob("/sys/class/drm/card[0-9]/device/gpu_busy_percent"):
            try:
                with open(path) as f:
                    values.append(float(f.read().strip()))
            except (OSError, ValueError):
                continue
        if not values:
            return None
        return min(max(values), 100.0)

    def _query_gpu_3d_linux(self) -> float:
        """Best-effort GPU utilization % on Linux: NVIDIA first, then AMD, else silent."""
        for query in (self._query_nvidia_smi, self._query_amdgpu_sysfs):
            value = query()
            if value is not None:
                return value
        return 0.0

    def run(self) -> None:
        if IS_WINDOWS:
            self._run_windows()
        else:
            self._run_linux()

    def _run_windows(self) -> None:
        # COM must be initialized on every thread that uses WMI
        pythoncom.CoInitialize()
        try:
            w = wmi.WMI(namespace="root\\cimv2")
            while not self._stop_event.wait(self._interval):
                try:
                    self._state.set_gpu_3d_percent(self._query_gpu_3d(w))
                except Exception:
                    self._state.set_gpu_3d_percent(0.0)
        except Exception:
            pass
        finally:
            pythoncom.CoUninitialize()

    def _run_linux(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self._state.set_gpu_3d_percent(self._query_gpu_3d_linux())
            except Exception:
                self._state.set_gpu_3d_percent(0.0)

    def stop(self) -> None:
        self._stop_event.set()
