import threading
import psutil
from shared_state import SharedState


class CpuPoller(threading.Thread):
    def __init__(self, state: SharedState, interval: float = 0.5):
        super().__init__(daemon=True)
        self._state = state
        self._interval = interval
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.wait(self._interval):
            cpu = psutil.cpu_percent()
            self._state.set_cpu(cpu)

    def stop(self) -> None:
        self._stop_event.set()
