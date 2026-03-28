import threading


class SharedState:
    def __init__(self):
        self._lock = threading.Lock()
        self._cpu_percent = 0.0
        self._volume = 50

    def get_cpu(self) -> float:
        with self._lock:
            return self._cpu_percent

    def set_cpu(self, value: float) -> None:
        with self._lock:
            self._cpu_percent = value

    def get_volume(self) -> int:
        with self._lock:
            return self._volume

    def set_volume(self, value: int) -> None:
        with self._lock:
            self._volume = int(value)
