import threading
import numpy as np
import sounddevice as sd
from shared_state import SharedState

SAMPLE_RATE = 44100
BLOCK_SIZE = 1024
SMOOTHING = 0.05
LFO_RATE = 7.0        # Hz — vibrato oscillation speed
MAX_CTX_RATE = 50000  # ctx/sec that maps to full vibrato depth
MAX_VIBRATO_DEPTH = 20.0  # Hz — max ± frequency deviation


class AudioEngine(threading.Thread):
    def __init__(self, state: SharedState):
        super().__init__(daemon=True)
        self._state = state
        self._stop_event = threading.Event()
        self._current_freq = 60.0
        self._phase = 0.0
        self._lfo_phase = 0.0

    def target_freq(self) -> float:
        cpu = self._state.get_cpu()
        return 60.0 + (cpu / 100.0) * 240.0

    def amplitude(self) -> float:
        return self._state.get_volume() / 100.0

    def vibrato_depth(self) -> float:
        ctx_rate = self._state.get_ctx_rate()
        normalized = min(ctx_rate / MAX_CTX_RATE, 1.0)
        return normalized * MAX_VIBRATO_DEPTH

    def _callback(self, outdata, frames, time_info, status):
        target = self.target_freq()
        self._current_freq += (target - self._current_freq) * SMOOTHING
        amp = self.amplitude()
        depth = self.vibrato_depth()

        t = np.arange(frames) / SAMPLE_RATE
        lfo = depth * np.sin(2 * np.pi * LFO_RATE * t + self._lfo_phase)
        wave = (amp * np.sin(2 * np.pi * self._current_freq * t + self._phase + np.cumsum(2 * np.pi * lfo / SAMPLE_RATE))).astype(np.float32)
        self._phase = (self._phase + 2 * np.pi * self._current_freq * frames / SAMPLE_RATE) % (2 * np.pi)
        self._lfo_phase = (self._lfo_phase + 2 * np.pi * LFO_RATE * frames / SAMPLE_RATE) % (2 * np.pi)

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
