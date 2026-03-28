import threading
import time
import psutil
from shared_state import SharedState


class CpuPoller(threading.Thread):
    def __init__(self, state: SharedState, interval: float = 0.5):
        super().__init__(daemon=True)
        self._state = state
        self._interval = interval
        self._stop_event = threading.Event()
        self._last_ctx = psutil.cpu_stats().ctx_switches
        self._last_time = time.monotonic()

    def run(self) -> None:
        while not self._stop_event.wait(self._interval):
            cpu = psutil.cpu_percent()
            self._state.set_cpu(cpu)

            now = time.monotonic()
            ctx = psutil.cpu_stats().ctx_switches
            elapsed = now - self._last_time
            if elapsed > 0:
                self._state.set_ctx_rate((ctx - self._last_ctx) / elapsed)
            self._last_ctx = ctx
            self._last_time = now

    def stop(self) -> None:
        self._stop_event.set()
