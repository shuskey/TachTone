import threading
import time
import psutil
from shared_state import SharedState

WIFI_ADAPTER = "Wi-Fi"  # Windows default Wi-Fi adapter name


class NetworkPoller(threading.Thread):
    def __init__(self, state: SharedState, interval: float = 0.5):
        super().__init__(daemon=True)
        self._state = state
        self._interval = interval
        self._stop_event = threading.Event()
        c = self._get_counters()
        self._last_recv = c.bytes_recv
        self._last_sent = c.bytes_sent
        self._last_time = time.monotonic()

    def _get_counters(self):
        per_nic = psutil.net_io_counters(pernic=True)
        if WIFI_ADAPTER in per_nic:
            return per_nic[WIFI_ADAPTER]
        return psutil.net_io_counters()  # fallback: sum all adapters

    def run(self) -> None:
        while not self._stop_event.wait(self._interval):
            now = time.monotonic()
            c = self._get_counters()
            elapsed = now - self._last_time
            if elapsed > 0:
                self._state.set_net_recv_rate(
                    max(0.0, (c.bytes_recv - self._last_recv) / elapsed)
                )
                self._state.set_net_send_rate(
                    max(0.0, (c.bytes_sent - self._last_sent) / elapsed)
                )
            self._last_recv = c.bytes_recv
            self._last_sent = c.bytes_sent
            self._last_time = now

    def stop(self) -> None:
        self._stop_event.set()
