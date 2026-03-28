import os
import socket
import threading

from shared_state import SharedState

HONK_PORT = int(os.environ.get("TACHTONE_HONK_PORT", 9876))


class HonkListener(threading.Thread):
    def __init__(self, state: SharedState):
        super().__init__(daemon=True)
        self._state = state
        self._stop_event = threading.Event()

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
                except socket.timeout:
                    continue

    def stop(self) -> None:
        self._stop_event.set()
