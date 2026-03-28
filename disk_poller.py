import threading
import time
import psutil
from shared_state import SharedState


class DiskPoller(threading.Thread):
    def __init__(self, state: SharedState, interval: float = 0.5):
        super().__init__(daemon=True)
        self._state = state
        self._interval = interval
        self._stop_event = threading.Event()
        c = psutil.disk_io_counters()
        self._last_read = c.read_bytes
        self._last_write = c.write_bytes
        self._last_time = time.monotonic()

    def run(self) -> None:
        while not self._stop_event.wait(self._interval):
            now = time.monotonic()
            c = psutil.disk_io_counters()
            elapsed = now - self._last_time
            if elapsed > 0:
                rate = (
                    (c.read_bytes - self._last_read) +
                    (c.write_bytes - self._last_write)
                ) / elapsed
                self._state.set_disk_rate(max(0.0, rate))
            self._last_read = c.read_bytes
            self._last_write = c.write_bytes
            self._last_time = now

    def stop(self) -> None:
        self._stop_event.set()
