import random
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
ENGINE_NOISE_AMP = 0.004  # mechanical noise floor

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

# GPU organ voice
GPU_SILENCE_THRESHOLD   = 5.0        # % — below this, organ stays silent
GPU_ORGAN_DECAY         = 1.8        # seconds — long sustain, chords overlap
GPU_VOICE_GAIN          = 0.30       # mix amplitude
GPU_VIBRATO_RATE        = 4.5        # Hz
GPU_TREMOLO_RATE        = 3.1        # Hz — intentionally non-integer vs vibrato
GPU_VIBRATO_DEPTH       = 0.004      # ±0.4% of note frequency
GPU_TREMOLO_DEPTH       = 0.25       # ±25% amplitude
GPU_WOBBLE_BEATS        = 4          # stable beats before wobble reaches full depth

# Quartal chords: 8 bands, 3 notes each stacked in perfect 4ths (5 semitones)
# Rooted on C major scale degrees, voiced C4–Bb5
GPU_CHORDS = [
    [261.63, 349.23, 466.16],   # C4 + F4  + Bb4   (0–12.5%)
    [293.66, 392.00, 523.25],   # D4 + G4  + C5    (12.5–25%)
    [329.63, 440.00, 587.33],   # E4 + A4  + D5    (25–37.5%)
    [349.23, 466.16, 622.25],   # F4 + Bb4 + Eb5   (37.5–50%)
    [392.00, 523.25, 698.46],   # G4 + C5  + F5    (50–62.5%)
    [440.00, 587.33, 783.99],   # A4 + D5  + G5    (62.5–75%)
    [493.88, 659.25, 880.00],   # B4 + E5  + A5    (75–87.5%)
    [523.25, 698.46, 932.33],   # C5 + F5  + Bb5   (87.5–100%)
]

# Organ timbre: partials 1–4, relatively equal weights
GPU_ORGAN_HARMONICS     = [1.0, 0.7, 0.5, 0.3]
GPU_ORGAN_HARMONICS_SUM = sum(GPU_ORGAN_HARMONICS)

# Beat voicings: which note indices (0=root, 1=4th, 2=top) to play each beat.
# Picked randomly on each beat so the chord breathes rather than droning.
GPU_BEAT_VOICINGS = [
    (0, 1, 2),  # full quartal chord
    (0, 1),     # root + fourth
    (1, 2),     # fourth + top
    (0, 2),     # root + top (open voicing)
]


def _gpu_band(gpu_percent: float) -> int:
    """Map GPU utilization % (0–100) to chord band index (0–7)."""
    return min(int(gpu_percent / 100.0 * 8), 7)


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
        # GPU organ voice
        self._gpu_band = 0
        self._gpu_organ_env = 0.0
        self._gpu_note_phases = [0.0] * 3
        self._gpu_stable_beats = 0
        self._gpu_vibrato_phase = 0.0
        self._gpu_tremolo_phase = 0.0
        self._gpu_active_voicing = GPU_BEAT_VOICINGS[0]

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

        # GPU organ — triggers every beat when above silence threshold
        if snap.gpu_3d_percent >= GPU_SILENCE_THRESHOLD:
            new_band = _gpu_band(snap.gpu_3d_percent)
            if new_band == self._gpu_band:
                self._gpu_stable_beats += 1
            else:
                # Step one band toward target per beat — smooth melodic motion,
                # never jumps more than one chord at a time regardless of load change
                step = 1 if new_band > self._gpu_band else -1
                self._gpu_band += step
                self._gpu_stable_beats = 0
                self._gpu_note_phases = [0.0] * 3
            # Pick a random voicing each beat so the chord breathes
            self._gpu_active_voicing = random.choice(GPU_BEAT_VOICINGS)
            self._gpu_organ_env = 1.0

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

    def _gpu_organ_block(self, frames: int) -> np.ndarray:
        """Quartal organ chord with layered vibrato + tremolo wobble."""
        if self._gpu_organ_env < 0.001:
            return np.zeros(frames, dtype=np.float32)

        chord = GPU_CHORDS[self._gpu_band]
        wobble = min(self._gpu_stable_beats / GPU_WOBBLE_BEATS, 1.0)
        TWO_PI = 2 * np.pi
        sample_idx = np.arange(frames)

        # Vibrato: slow LFO modulates each note's frequency ±GPU_VIBRATO_DEPTH
        vibrato = GPU_VIBRATO_DEPTH * wobble * np.sin(
            TWO_PI * GPU_VIBRATO_RATE * sample_idx / SAMPLE_RATE
            + self._gpu_vibrato_phase
        )

        # Tremolo: slower LFO pulses amplitude ±GPU_TREMOLO_DEPTH
        tremolo = 1.0 - GPU_TREMOLO_DEPTH * wobble * 0.5 * (
            1.0 - np.cos(
                TWO_PI * GPU_TREMOLO_RATE * sample_idx / SAMPLE_RATE
                + self._gpu_tremolo_phase
            )
        )

        # Decaying amplitude envelope
        env = self._gpu_organ_env * np.exp(
            -sample_idx / (GPU_ORGAN_DECAY * SAMPLE_RATE)
        )

        wave = np.zeros(frames)
        for i, f in enumerate(chord):
            # Always advance phase to stay continuous, but only add to mix if active
            inst_freq = f * (1.0 + vibrato)
            fund_phase_arr = self._gpu_note_phases[i] + np.cumsum(
                TWO_PI * inst_freq / SAMPLE_RATE
            )
            if i in self._gpu_active_voicing:
                # Organ harmonics: harmonic n uses n × fundamental phase
                note_wave = np.zeros(frames)
                for n, w in enumerate(GPU_ORGAN_HARMONICS, start=1):
                    note_wave += w * np.sin(n * fund_phase_arr)
                note_wave /= GPU_ORGAN_HARMONICS_SUM
                wave += note_wave
            self._gpu_note_phases[i] = float(fund_phase_arr[-1]) % TWO_PI

        wave /= len(self._gpu_active_voicing)
        wave *= env * tremolo

        # Advance envelope and LFO phases for next block
        self._gpu_organ_env *= float(
            np.exp(-frames / (GPU_ORGAN_DECAY * SAMPLE_RATE))
        )
        self._gpu_vibrato_phase = (
            self._gpu_vibrato_phase
            + TWO_PI * GPU_VIBRATO_RATE * frames / SAMPLE_RATE
        ) % TWO_PI
        self._gpu_tremolo_phase = (
            self._gpu_tremolo_phase
            + TWO_PI * GPU_TREMOLO_RATE * frames / SAMPLE_RATE
        ) % TWO_PI

        return wave.astype(np.float32)

    def _make_honk_segment(self, duration_samples: int) -> np.ndarray:
        t = np.arange(duration_samples) / SAMPLE_RATE
        env = np.ones(duration_samples)
        attack = min(HONK_ATTACK, duration_samples // 4)
        release = min(HONK_RELEASE, duration_samples // 4)
        env[:attack] = np.linspace(0.0, 1.0, attack)
        env[-release:] = np.linspace(1.0, 0.0, release)
        return env * 0.5 * (np.sin(2 * np.pi * HONK_FREQ1 * t) +
                             np.sin(2 * np.pi * HONK_FREQ2 * t))

    def _trigger_honk(self) -> None:
        """Pre-render the full honk-honk waveform and reset playback position."""
        honk = self._make_honk_segment(HONK_DURATION)
        gap = np.zeros(HONK_GAP)
        self._honk_buffer = np.concatenate([honk, gap, honk]).astype(np.float32)
        self._honk_pos = 0

    def _trigger_impatient_honk(self) -> None:
        """Pre-render the grouchy multi-honk sequence: cluster + long lean + cluster + medium."""
        short_gap = np.zeros(HONK_GAP)
        long_gap  = np.zeros(int(SAMPLE_RATE * 0.35))

        def cluster(n: int) -> list:
            parts = []
            for i in range(n):
                parts.append(self._make_honk_segment(HONK_DURATION))
                if i < n - 1:
                    parts.append(short_gap)
            return parts

        parts = []
        parts.extend(cluster(random.randint(3, 4)))
        parts.append(long_gap)
        parts.append(self._make_honk_segment(int(SAMPLE_RATE * random.uniform(4.5, 5.5))))
        parts.append(long_gap)
        parts.extend(cluster(random.randint(3, 4)))
        parts.append(long_gap)
        parts.append(self._make_honk_segment(int(SAMPLE_RATE * random.uniform(1.8, 2.2))))

        self._honk_buffer = np.concatenate(parts).astype(np.float32)
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

        # Honk triggers
        if snap.honk:
            self._state.set_honk(False)
            self._trigger_honk()
        elif snap.impatient_honk:
            self._state.set_impatient_honk(False)
            self._trigger_impatient_honk()

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
        gpu_ch   = snap.gpu_vol / 100.0

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
        gpu_organ = self._gpu_organ_block(frames)

        total = (tach
                 + master * NET_VOICE_GAIN * net_ch * (bell + piano)
                 + master * TOM_VOICE_GAIN * disk_ch * tom
                 + master * honk_ch * honk
                 + master * GPU_VOICE_GAIN * gpu_ch * gpu_organ)
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
