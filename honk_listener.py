import os
import socket
import threading

from shared_state import SharedState

HONK_PORT = int(os.environ.get("TACHTONE_HONK_PORT", 9876))
IMPATIENT_DELAY = 30.0  # seconds before impatient sequence fires


class HonkListener(threading.Thread):
    def __init__(self, state: SharedState):
        super().__init__(daemon=True)
        self._state = state
        self._stop_event = threading.Event()
        self._impatient_timer: threading.Timer | None = None
        self._timer_lock = threading.Lock()

    def run(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(1.0)
            sock.bind(("127.0.0.1", HONK_PORT))
            while not self._stop_event.is_set():
                try:
                    data, _ = sock.recvfrom(64)
                    if data == b"honk":
                        self._state.set_honk(True)
                        self._restart_impatient_timer()
                    elif data == b"cancel":
                        self._cancel_impatient_timer()
                except socket.timeout:
                    continue

    def _restart_impatient_timer(self) -> None:
        with self._timer_lock:
            if self._impatient_timer is not None:
                self._impatient_timer.cancel()
            if self._state.get_impatient_honking_enabled():
                self._impatient_timer = threading.Timer(IMPATIENT_DELAY, self._on_timeout)
                self._impatient_timer.daemon = True
                self._impatient_timer.start()

    def _cancel_impatient_timer(self) -> None:
        with self._timer_lock:
            if self._impatient_timer is not None:
                self._impatient_timer.cancel()
                self._impatient_timer = None

    def _on_timeout(self) -> None:
        with self._timer_lock:
            self._impatient_timer = None
        self._state.set_impatient_honk(True)

    def stop(self) -> None:
        self._cancel_impatient_timer()
        self._stop_event.set()
