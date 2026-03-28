import threading
import numpy as np
import sounddevice as sd
from shared_state import SharedState

SAMPLE_RATE = 44100
BLOCK_SIZE = 1024
SMOOTHING = 0.02      # slower than before — engines have rotational inertia
LFO_RATE = 7.0        # Hz — RPM-hunt oscillation speed
MAX_CTX_RATE = 50000  # ctx/sec that maps to full RPM instability

# Engine simulation
ENGINE_IDLE_RPM = 700
ENGINE_MAX_RPM  = 7000
# Harmonic weights for a 4-cylinder (even harmonics = firing pulses, boosted)
ENGINE_HARMONICS     = [0.30, 1.00, 0.45, 0.80, 0.25, 0.55, 0.15, 0.35]
ENGINE_HARMONICS_SUM = sum(ENGINE_HARMONICS)
ENGINE_AM_DEPTH  = 0.40   # max amplitude-modulation depth at idle (chug)
ENGINE_NOISE_AMP = 0.018  # mechanical noise floor

# Network note voices
BPM = 80
BEAT_SAMPLES = int(SAMPLE_RATE * 60 / BPM)
NET_MAX_RATE = 500_000        # bytes/sec → top of note range
NET_SILENCE_THRESHOLD = 5_000 # bytes/sec below this → no note
NET_VOICE_GAIN = 0.27         # amplitude of each network voice (0.45 * 0.6)

# C major scale, C5–C6 (above tach tone range)
NOTE_FREQS = [523.25, 587.33, 659.25, 698.46, 783.99, 880.00, 987.77, 1046.50]

BELL_DECAY = 0.05   # seconds — incoming traffic (bell)
PIANO_DECAY = 0.03  # seconds — outgoing traffic (piano)

# Car horn honk voice (two-tone, classic US horn)
HONK_FREQ1    = 392.0              # G4
HONK_FREQ2    = 494.0              # B4
HONK_DURATION = int(SAMPLE_RATE * 0.18)   # 180 ms per honk
HONK_GAP      = int(SAMPLE_RATE * 0.09)   # 90 ms silence between honks
HONK_ATTACK   = int(SAMPLE_RATE * 0.010)  # 10 ms attack
HONK_RELEASE  = int(SAMPLE_RATE * 0.025)  # 25 ms release

# Disk tom-tom voice
DISK_BEAT_SAMPLES = BEAT_SAMPLES // 4   # 4x faster = 16th notes at 80 BPM
DISK_MAX_RATE = 10_000_000              # 10 MB/s → top tom pitch
DISK_SILENCE_THRESHOLD = 100_000        # 100 KB/s dead zone
TOM_FREQS = [80, 100, 120, 140, 165, 190, 215, 250]  # Hz, low → high tom
TOM_DECAY = 0.07          # seconds — short thud
TOM_PITCH_SWEEP = 0.025   # seconds — pitch drops from +25 Hz to target
TOM_PITCH_EXTRA = 25.0    # Hz above target at moment of hit
TOM_VOICE_GAIN = 0.35


class AudioEngine(threading.Thread):
    def __init__(self, state: SharedState):
        super().__init__(daemon=True)
        self._state = state
        self._stop_event = threading.Event()
        self._current_freq = ENGINE_IDLE_RPM / 60.0
        self._phase = 0.0
        self._lfo_phase = 0.0
        self._am_phase = 0.0
        # Network beat clock
        self._beat_samples_left = BEAT_SAMPLES
        # Disk beat clock (4x faster)
        self._disk_beat_samples_left = DISK_BEAT_SAMPLES
        # Tom-tom voice (disk activity)
        self._tom_freq = TOM_FREQS[0]
        self._tom_env = 0.0
        self._tom_phase = 0.0
        self._tom_pitch_extra = 0.0
        # Bell voice (incoming network)
        self._bell_freq = NOTE_FREQS[0]
        self._bell_env = 0.0
        self._bell_phase = 0.0
        # Piano voice (outgoing network)
        self._piano_freq = NOTE_FREQS[0]
        self._piano_env = 0.0
        self._piano_phase = 0.0
        # Car horn voice
        self._honk_buffer: np.ndarray | None = None
        self._honk_pos = 0

    def target_freq(self) -> float:
        """Returns crankshaft frequency in Hz based on CPU load mapped to RPM."""
        cpu = self._state.get_cpu()
        rpm = ENGINE_IDLE_RPM + (cpu / 100.0) * (ENGINE_MAX_RPM - ENGINE_IDLE_RPM)
        return rpm / 60.0

    def _note_band(self, rate: float) -> int:
        return min(int(rate / NET_MAX_RATE * 8), 7)

    def _on_beat(self, snap) -> None:
        if snap.net_recv_rate > NET_SILENCE_THRESHOLD:
            self._bell_freq = NOTE_FREQS[self._note_band(snap.net_recv_rate)]
            self._bell_env = 1.0
            self._bell_phase = 0.0
        if snap.net_send_rate > NET_SILENCE_THRESHOLD:
            self._piano_freq = NOTE_FREQS[self._note_band(snap.net_send_rate)]
            self._piano_env = 1.0
            self._piano_phase = 0.0

    def _bell_block(self, frames: int) -> np.ndarray:
        """Bell timbre: soft sine + 2 gentle harmonics, slow decay."""
        if self._bell_env < 0.001:
            return np.zeros(frames, dtype=np.float32)
        t = np.arange(frames) / SAMPLE_RATE
        env = self._bell_env * np.exp(-np.arange(frames) / (BELL_DECAY * SAMPLE_RATE))
        f, p = self._bell_freq, self._bell_phase
        TWO_PI = 2 * np.pi
        wave = (
            1.00 * np.sin(TWO_PI * f * t + p) +
            0.25 * np.sin(TWO_PI * 2 * f * t + 2 * p) +
            0.10 * np.sin(TWO_PI * 3 * f * t + 3 * p)
        ) * env / 1.35
        self._bell_phase = (p + TWO_PI * f * frames / SAMPLE_RATE) % TWO_PI
        self._bell_env *= np.exp(-frames / (BELL_DECAY * SAMPLE_RATE))
        return wave.astype(np.float32)

    def _piano_block(self, frames: int) -> np.ndarray:
        """Piano timbre: brighter harmonics, faster percussive decay."""
        if self._piano_env < 0.001:
            return np.zeros(frames, dtype=np.float32)
        t = np.arange(frames) / SAMPLE_RATE
        env = self._piano_env * np.exp(-np.arange(frames) / (PIANO_DECAY * SAMPLE_RATE))
        f, p = self._piano_freq, self._piano_phase
        TWO_PI = 2 * np.pi
        wave = (
            1.00 * np.sin(TWO_PI * f * t + p) +
            0.60 * np.sin(TWO_PI * 2 * f * t + 2 * p) +
            0.35 * np.sin(TWO_PI * 3 * f * t + 3 * p) +
            0.15 * np.sin(TWO_PI * 4 * f * t + 4 * p)
        ) * env / 2.10
        self._piano_phase = (p + TWO_PI * f * frames / SAMPLE_RATE) % TWO_PI
        self._piano_env *= np.exp(-frames / (PIANO_DECAY * SAMPLE_RATE))
        return wave.astype(np.float32)

    def _on_disk_beat(self, snap) -> None:
        if snap.disk_rate > DISK_SILENCE_THRESHOLD:
            band = min(int(snap.disk_rate / DISK_MAX_RATE * 8), 7)
            self._tom_freq = TOM_FREQS[band]
            self._tom_env = 1.0
            self._tom_phase = 0.0
            self._tom_pitch_extra = TOM_PITCH_EXTRA

    def _tom_block(self, frames: int) -> np.ndarray:
        """Tom-tom timbre: sine with fast decay and pitch drop on hit."""
        if self._tom_env < 0.001:
            return np.zeros(frames, dtype=np.float32)
        sample_idx = np.arange(frames)
        # Pitch sweep: extra Hz drops to zero over TOM_PITCH_SWEEP seconds
        pitch_extra = self._tom_pitch_extra * np.exp(-sample_idx / (TOM_PITCH_SWEEP * SAMPLE_RATE))
        inst_freq = self._tom_freq + pitch_extra
        # Amplitude envelope
        env = self._tom_env * np.exp(-sample_idx / (TOM_DECAY * SAMPLE_RATE))
        # Phase accumulation with time-varying frequency
        phase_acc = self._tom_phase + 2 * np.pi / SAMPLE_RATE * np.cumsum(inst_freq)
        wave = (np.sin(phase_acc) * env).astype(np.float32)
        # Update state for next block
        self._tom_phase = float(phase_acc[-1]) % (2 * np.pi)
        self._tom_env *= float(np.exp(-frames / (TOM_DECAY * SAMPLE_RATE)))
        self._tom_pitch_extra *= float(np.exp(-frames / (TOM_PITCH_SWEEP * SAMPLE_RATE)))
        return wave

    def _trigger_honk(self) -> None:
        """Pre-render the full honk-honk waveform and reset playback position."""
        t = np.arange(HONK_DURATION) / SAMPLE_RATE
        env = np.ones(HONK_DURATION)
        env[:HONK_ATTACK] = np.linspace(0.0, 1.0, HONK_ATTACK)
        env[-HONK_RELEASE:] = np.linspace(1.0, 0.0, HONK_RELEASE)
        honk = env * 0.5 * (np.sin(2 * np.pi * HONK_FREQ1 * t) +
                             np.sin(2 * np.pi * HONK_FREQ2 * t))
        gap = np.zeros(HONK_GAP)
        self._honk_buffer = np.concatenate([honk, gap, honk]).astype(np.float32)
        self._honk_pos = 0

    def _honk_block(self, frames: int) -> np.ndarray:
        if self._honk_buffer is None or self._honk_pos >= len(self._honk_buffer):
            return np.zeros(frames, dtype=np.float32)
        remaining = len(self._honk_buffer) - self._honk_pos
        chunk = min(frames, remaining)
        out = np.zeros(frames, dtype=np.float32)
        out[:chunk] = self._honk_buffer[self._honk_pos:self._honk_pos + chunk]
        self._honk_pos += chunk
        return out

    def vibrato_depth(self) -> float:
        """RPM instability: up to ±5% of current crank frequency."""
        ctx_rate = self._state.get_ctx_rate()
        normalized = min(ctx_rate / MAX_CTX_RATE, 1.0)
        interrupts_ch = self._state.get_interrupts_vol() / 100.0
        return normalized * self._current_freq * 0.05 * interrupts_ch

    def _callback(self, outdata, frames, time_info, status):
        snap = self._state.snapshot()

        # Honk trigger (one write lock if needed)
        if snap.honk:
            self._state.set_honk(False)
            self._trigger_honk()

        # Network beat clock (quarter notes)
        self._beat_samples_left -= frames
        while self._beat_samples_left <= 0:
            self._beat_samples_left += BEAT_SAMPLES
            self._on_beat(snap)
        # Disk beat clock (16th notes — 4x faster)
        self._disk_beat_samples_left -= frames
        while self._disk_beat_samples_left <= 0:
            self._disk_beat_samples_left += DISK_BEAT_SAMPLES
            self._on_disk_beat(snap)

        # Channel volumes
        master   = snap.volume / 100.0
        cpu_ch   = snap.cpu_vol / 100.0
        net_ch   = snap.network_vol / 100.0
        disk_ch  = snap.disk_vol / 100.0
        honk_ch  = snap.honk_vol / 100.0

        # Engine tone (CPU load → RPM → harmonic stack + AM chug + noise)
        rpm = ENGINE_IDLE_RPM + (snap.cpu_percent / 100.0) * (ENGINE_MAX_RPM - ENGINE_IDLE_RPM)
        target = rpm / 60.0
        self._current_freq += (target - self._current_freq) * SMOOTHING
        f = self._current_freq
        normalized = min(snap.ctx_rate / MAX_CTX_RATE, 1.0)
        depth = normalized * self._current_freq * 0.05 * (snap.interrupts_vol / 100.0)

        t = np.arange(frames) / SAMPLE_RATE

        # RPM instability (context-switch LFO) — modulates crank frequency ±depth Hz
        lfo = depth * np.sin(2 * np.pi * LFO_RATE * t + self._lfo_phase)

        # Continuous phase accumulation for fundamental (with LFO)
        fund_phase_arr = self._phase + np.cumsum(2 * np.pi * (f + lfo) / SAMPLE_RATE)

        # Harmonic stack (4-cylinder profile: even harmonics = firing pulses)
        tach_raw = np.zeros(frames)
        for n, w in enumerate(ENGINE_HARMONICS, start=1):
            tach_raw += w * np.sin(n * fund_phase_arr)
        tach_raw /= ENGINE_HARMONICS_SUM

        # Amplitude modulation at firing frequency (4-cyl fires at 2× crank)
        # Fades from full chug at idle to silent at ~67% CPU
        am_depth = ENGINE_AM_DEPTH * max(0.0, 1.0 - snap.cpu_percent / 67.0)
        am_phase_arr = self._am_phase + 2 * np.pi * (2.0 * f) * t
        tach_raw *= 1.0 - am_depth * 0.5 * (1.0 - np.cos(am_phase_arr))

        # Mechanical noise floor
        tach_raw += ENGINE_NOISE_AMP * np.random.randn(frames)

        tach = (master * cpu_ch * tach_raw).astype(np.float32)

        # Advance phases
        self._phase = float(fund_phase_arr[-1]) % (2 * np.pi)
        self._lfo_phase = (self._lfo_phase + 2 * np.pi * LFO_RATE * frames / SAMPLE_RATE) % (2 * np.pi)
        self._am_phase = float(am_phase_arr[-1]) % (2 * np.pi)

        # Network, disk, and honk voices (master scales all channels uniformly)
        bell  = self._bell_block(frames)
        piano = self._piano_block(frames)
        tom   = self._tom_block(frames)
        honk  = self._honk_block(frames)

        total = (tach
                 + master * NET_VOICE_GAIN * net_ch * (bell + piano)
                 + master * TOM_VOICE_GAIN * disk_ch * tom
                 + master * honk_ch * honk)
        outdata[:, 0] = np.clip(total, -1.0, 1.0).astype(np.float32)

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
