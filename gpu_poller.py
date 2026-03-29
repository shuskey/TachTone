import threading

import pythoncom
import wmi

from shared_state import SharedState


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

    def run(self) -> None:
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

    def stop(self) -> None:
        self._stop_event.set()
