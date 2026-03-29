import os
import socket
import threading

from shared_state import SharedState

HONK_PORT = int(os.environ.get("TACHTONE_HONK_PORT", 9876))
IMPATIENT_DELAY = 30.0   # seconds before impatient sequence fires
APPROVAL_WAIT   =  8.0   # seconds before assuming Claude is waiting for tool approval


class HonkListener(threading.Thread):
    def __init__(self, state: SharedState):
        super().__init__(daemon=True)
        self._state = state
        self._stop_event = threading.Event()
        self._impatient_timer: threading.Timer | None = None
        self._timer_lock = threading.Lock()
        self._approval_timer: threading.Timer | None = None
        self._approval_lock = threading.Lock()

    def run(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(1.0)
            sock.bind(("127.0.0.1", HONK_PORT))
            while not self._stop_event.is_set():
                try:
                    data, _ = sock.recvfrom(64)
                    if data == b"need attention":
                        self._state.set_honk(True)
                        self._restart_impatient_timer()
                    elif data == b"got attention":
                        self._cancel_impatient_timer()
                        self._cancel_approval_timer()
                    elif data == b"claude task complete":
                        self._cancel_impatient_timer()
                        self._cancel_approval_timer()
                        self._state.set_honk(True)
                    elif data == b"pre_tool_use":
                        self._cancel_impatient_timer()
                        self._restart_approval_timer()
                    elif data == b"post_tool_use":
                        self._cancel_approval_timer()
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

    def _restart_approval_timer(self) -> None:
        with self._approval_lock:
            if self._approval_timer is not None:
                self._approval_timer.cancel()
            if self._state.get_impatient_honking_enabled():
                self._approval_timer = threading.Timer(APPROVAL_WAIT, self._on_approval_timeout)
                self._approval_timer.daemon = True
                self._approval_timer.start()

    def _cancel_approval_timer(self) -> None:
        with self._approval_lock:
            if self._approval_timer is not None:
                self._approval_timer.cancel()
                self._approval_timer = None

    def _on_approval_timeout(self) -> None:
        with self._approval_lock:
            self._approval_timer = None
        self._state.set_honk(True)
        self._restart_impatient_timer()

    def stop(self) -> None:
        self._cancel_impatient_timer()
        self._cancel_approval_timer()
        self._stop_event.set()
