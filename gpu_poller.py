import threading

import wmi

from shared_state import SharedState


class GpuPoller(threading.Thread):
    def __init__(self, state: SharedState, interval: float = 0.5):
        super().__init__(daemon=True)
        self._state = state
        self._interval = interval
        self._stop_event = threading.Event()

    def _query_gpu_3d(self) -> float:
        """Return total GPU 3D engine utilization % via Windows Performance Counters."""
        try:
            w = wmi.WMI(namespace="root\\cimv2")
            entries = w.Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine()
            total = sum(
                int(e.UtilizationPercentage)
                for e in entries
                if "engtype_3D" in e.Name
            )
            return min(float(total), 100.0)
        except Exception:
            return 0.0

    def run(self) -> None:
        while not self._stop_event.wait(self._interval):
            self._state.set_gpu_3d_percent(self._query_gpu_3d())

    def stop(self) -> None:
        self._stop_event.set()
