import threading
import numpy as np
import sounddevice as sd
from shared_state import SharedState

SAMPLE_RATE = 44100
BLOCK_SIZE = 1024
SMOOTHING = 0.05


class AudioEngine(threading.Thread):
    def __init__(self, state: SharedState):
        super().__init__(daemon=True)
        self._state = state
        self._stop_event = threading.Event()
        self._current_freq = 60.0
        self._phase = 0.0

    def target_freq(self) -> float:
        cpu = self._state.get_cpu()
        return 60.0 + (cpu / 100.0) * 240.0

    def amplitude(self) -> float:
        return self._state.get_volume() / 100.0

    def _callback(self, outdata, frames, time_info, status):
        target = self.target_freq()
        self._current_freq += (target - self._current_freq) * SMOOTHING
        amp = self.amplitude()

        t = (self._phase + np.arange(frames)) / SAMPLE_RATE
        wave = amp * np.sin(2 * np.pi * self._current_freq * t).astype(np.float32)
        self._phase = (self._phase + frames) % SAMPLE_RATE

        outdata[:, 0] = wave

    def run(self) -> None:
        with sd.OutputStream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            channels=1,
            dtype="float32",
            callback=self._callback,
        ):
            self._stop_event.wait()

    def stop(self) -> None:
        self._stop_event.set()
