import threading
from dataclasses import dataclass


@dataclass
class StateSnapshot:
    cpu_percent: float
    volume: int
    ctx_rate: float
    net_recv_rate: float
    net_send_rate: float
    disk_rate: float
    cpu_vol: int
    interrupts_vol: int
    network_vol: int
    disk_vol: int
    honk_vol: int
    honk: bool


class SharedState:
    """Thread-safe container for cpu_percent and volume."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cpu_percent = 0.0
        self._volume = 50
        self._ctx_rate = 0.0
        self._net_recv_rate = 0.0
        self._net_send_rate = 0.0
        self._disk_rate = 0.0
        # Per-channel volumes (0–100)
        self._cpu_vol = 80
        self._interrupts_vol = 12
        self._network_vol = 50
        self._disk_vol = 50
        self._honk_vol = 100
        # Honk trigger flag
        self._honk = False

    def _get(self, attr):
        with self._lock:
            return getattr(self, attr)

    def _set(self, attr, value, cast):
        with self._lock:
            setattr(self, attr, cast(value))

    def get_cpu(self) -> float:            return self._get('_cpu_percent')
    def set_cpu(self, v: float) -> None:   self._set('_cpu_percent', v, float)

    def get_ctx_rate(self) -> float:            return self._get('_ctx_rate')
    def set_ctx_rate(self, v: float) -> None:   self._set('_ctx_rate', v, float)

    def get_net_recv_rate(self) -> float:            return self._get('_net_recv_rate')
    def set_net_recv_rate(self, v: float) -> None:   self._set('_net_recv_rate', v, float)

    def get_net_send_rate(self) -> float:            return self._get('_net_send_rate')
    def set_net_send_rate(self, v: float) -> None:   self._set('_net_send_rate', v, float)

    def get_disk_rate(self) -> float:            return self._get('_disk_rate')
    def set_disk_rate(self, v: float) -> None:   self._set('_disk_rate', v, float)

    def get_volume(self) -> int:             return self._get('_volume')
    def set_volume(self, v: int) -> None:    self._set('_volume', v, int)

    def get_cpu_vol(self) -> int:            return self._get('_cpu_vol')
    def set_cpu_vol(self, v: int) -> None:   self._set('_cpu_vol', v, int)

    def get_interrupts_vol(self) -> int:            return self._get('_interrupts_vol')
    def set_interrupts_vol(self, v: int) -> None:   self._set('_interrupts_vol', v, int)

    def get_network_vol(self) -> int:            return self._get('_network_vol')
    def set_network_vol(self, v: int) -> None:   self._set('_network_vol', v, int)

    def get_disk_vol(self) -> int:            return self._get('_disk_vol')
    def set_disk_vol(self, v: int) -> None:   self._set('_disk_vol', v, int)

    def get_honk_vol(self) -> int:            return self._get('_honk_vol')
    def set_honk_vol(self, v: int) -> None:   self._set('_honk_vol', v, int)

    def get_honk(self) -> bool:              return self._get('_honk')
    def set_honk(self, v: bool) -> None:     self._set('_honk', v, bool)

    def snapshot(self) -> StateSnapshot:
        with self._lock:
            return StateSnapshot(
                cpu_percent=self._cpu_percent,
                volume=self._volume,
                ctx_rate=self._ctx_rate,
                net_recv_rate=self._net_recv_rate,
                net_send_rate=self._net_send_rate,
                disk_rate=self._disk_rate,
                cpu_vol=self._cpu_vol,
                interrupts_vol=self._interrupts_vol,
                network_vol=self._network_vol,
                disk_vol=self._disk_vol,
                honk_vol=self._honk_vol,
                honk=self._honk,
            )
