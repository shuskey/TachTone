# GPU Organ Channel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a GPU 3D load monitoring channel that plays ethereal quartal organ chords, with layered vibrato+tremolo wobble that intensifies during sustained load.

**Architecture:** A new `GpuPoller` thread queries Windows Performance Counters via `wmi` every 500ms and writes `gpu_3d_percent` to `SharedState`. The `AudioEngine` maps GPU % to one of eight quartal chords, triggers the chord on the existing network beat clock, and applies vibrato+tremolo wobble that ramps up over 4 stable beats.

**Tech Stack:** Python `wmi` (Windows Performance Counters), numpy (audio synthesis), existing `threading.Event` pattern for pollers.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `requirements.txt` | Modify | Add `wmi` dependency |
| `shared_state.py` | Modify | Add `gpu_3d_percent`, `gpu_vol` fields, accessors, snapshot |
| `gpu_poller.py` | Create | WMI GPU 3D polling thread |
| `audio_engine.py` | Modify | GPU organ voice, quartal chords, wobble, beat trigger |
| `tray_app.py` | Modify | GPU Organ volume slider |
| `main.py` | Modify | Instantiate and start GpuPoller |
| `tests/test_gpu_poller.py` | Create | Unit tests for GpuPoller |
| `tests/test_audio_engine.py` | Modify | Tests for GPU organ voice |

---

## Task 1: Extend SharedState with GPU Fields

**Files:**
- Modify: `shared_state.py`
- Modify: `tests/test_shared_state.py`

- [ ] **Step 1: Write failing tests**

Add to the bottom of `tests/test_shared_state.py`:

```python
def test_gpu_3d_percent_defaults_to_zero():
    state = SharedState()
    assert state.get_gpu_3d_percent() == 0.0


def test_gpu_vol_defaults_to_50():
    state = SharedState()
    assert state.get_gpu_vol() == 50


def test_gpu_3d_percent_round_trips():
    state = SharedState()
    state.set_gpu_3d_percent(73.5)
    assert state.get_gpu_3d_percent() == 73.5


def test_snapshot_includes_gpu_fields():
    state = SharedState()
    state.set_gpu_3d_percent(42.0)
    state.set_gpu_vol(75)
    snap = state.snapshot()
    assert snap.gpu_3d_percent == 42.0
    assert snap.gpu_vol == 75
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/test_shared_state.py -v -k "gpu"
```
Expected: `AttributeError` — method doesn't exist yet.

- [ ] **Step 3: Add fields to StateSnapshot dataclass**

In `shared_state.py`, add two fields at the end of the `StateSnapshot` dataclass:

```python
    gpu_3d_percent: float
    gpu_vol: int
```

- [ ] **Step 4: Add to SharedState.__init__**

Add inside `__init__`, after the honk fields:

```python
        self._gpu_3d_percent = 0.0
        self._gpu_vol = 50
```

- [ ] **Step 5: Add accessors**

Add after the `get_honk_vol`/`set_honk_vol` pair:

```python
    def get_gpu_3d_percent(self) -> float:           return self._get('_gpu_3d_percent')
    def set_gpu_3d_percent(self, v: float) -> None:  self._set('_gpu_3d_percent', v, float)

    def get_gpu_vol(self) -> int:            return self._get('_gpu_vol')
    def set_gpu_vol(self, v: int) -> None:   self._set('_gpu_vol', v, int)
```

- [ ] **Step 6: Add fields to snapshot()**

In the `snapshot()` return, add before the closing parenthesis:

```python
                gpu_3d_percent=self._gpu_3d_percent,
                gpu_vol=self._gpu_vol,
```

- [ ] **Step 7: Run tests to verify they pass**

```
pytest tests/test_shared_state.py -v -k "gpu"
```
Expected: 4 PASS

- [ ] **Step 8: Run full suite**

```
pytest tests/ -v
```
Expected: all PASS (existing tests unchanged)

- [ ] **Step 9: Commit**

```bash
git add shared_state.py tests/test_shared_state.py
git commit -m "feat: add gpu_3d_percent and gpu_vol to SharedState"
```

---

## Task 2: Create GpuPoller

**Files:**
- Create: `gpu_poller.py`
- Create: `tests/test_gpu_poller.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add wmi to requirements.txt**

Append to `requirements.txt`:

```
wmi
```

- [ ] **Step 2: Install it**

```
pip install wmi
```

- [ ] **Step 3: Write failing tests**

Create `tests/test_gpu_poller.py`:

```python
import time
from unittest.mock import MagicMock, patch

from shared_state import SharedState
from gpu_poller import GpuPoller


def _make_entry(name: str, utilization: int) -> MagicMock:
    e = MagicMock()
    e.Name = name
    e.UtilizationPercentage = str(utilization)
    return e


def _mock_wmi(entries):
    """Return a context-manager-friendly patch for gpu_poller.wmi.WMI."""
    instance = MagicMock()
    instance.Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine.return_value = entries
    return patch("gpu_poller.wmi.WMI", return_value=instance)


def test_query_sums_3d_engines():
    entries = [
        _make_entry("pid_123_luid_0_phys_0_eng_0_engtype_3D", 30),
        _make_entry("pid_456_luid_0_phys_0_eng_1_engtype_3D", 25),
        _make_entry("pid_789_luid_0_phys_0_eng_0_engtype_VideoDecode", 10),
    ]
    with _mock_wmi(entries):
        result = GpuPoller(SharedState())._query_gpu_3d()
    assert result == 55.0  # 30+25 only; VideoDecode excluded


def test_query_ignores_non_3d_engines():
    entries = [
        _make_entry("pid_1_luid_0_phys_0_eng_0_engtype_Copy", 50),
        _make_entry("pid_2_luid_0_phys_0_eng_0_engtype_VideoDecode", 40),
    ]
    with _mock_wmi(entries):
        result = GpuPoller(SharedState())._query_gpu_3d()
    assert result == 0.0


def test_query_caps_at_100():
    entries = [
        _make_entry("pid_1_luid_0_phys_0_eng_0_engtype_3D", 80),
        _make_entry("pid_2_luid_0_phys_0_eng_0_engtype_3D", 60),
    ]
    with _mock_wmi(entries):
        result = GpuPoller(SharedState())._query_gpu_3d()
    assert result == 100.0


def test_query_returns_zero_on_exception():
    with patch("gpu_poller.wmi.WMI", side_effect=Exception("WMI unavailable")):
        result = GpuPoller(SharedState())._query_gpu_3d()
    assert result == 0.0


def test_poller_updates_shared_state():
    state = SharedState()
    entries = [_make_entry("pid_1_luid_0_phys_0_eng_0_engtype_3D", 65)]
    with _mock_wmi(entries):
        poller = GpuPoller(state, interval=0.05)
        poller.start()
        time.sleep(0.15)
        poller.stop()
        poller.join(timeout=1.0)
    assert state.get_gpu_3d_percent() == 65.0


def test_poller_stops_cleanly():
    state = SharedState()
    with _mock_wmi([]):
        poller = GpuPoller(state, interval=0.05)
        poller.start()
        time.sleep(0.1)
        poller.stop()
        poller.join(timeout=1.0)
    assert not poller.is_alive()
```

- [ ] **Step 4: Run to verify failure**

```
pytest tests/test_gpu_poller.py -v
```
Expected: `ModuleNotFoundError` — `gpu_poller` doesn't exist yet.

- [ ] **Step 5: Create gpu_poller.py**

```python
import threading

import wmi

from shared_state import SharedState


class GpuPoller(threading.Thread):
    def __init__(self, state: SharedState, interval: float = 0.5):
        super().__init__(daemon=True)
        self._state = state
        self._interval = interval
        self._stop_event = threading.Event()

    def _query_gpu_3d(self) -> float:
        """Return total GPU 3D engine utilization % via Windows Performance Counters."""
        try:
            w = wmi.WMI(namespace="root\\cimv2")
            entries = w.Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine()
            total = sum(
                int(e.UtilizationPercentage)
                for e in entries
                if "engtype_3D" in e.Name
            )
            return min(float(total), 100.0)
        except Exception:
            return 0.0

    def run(self) -> None:
        while not self._stop_event.wait(self._interval):
            self._state.set_gpu_3d_percent(self._query_gpu_3d())

    def stop(self) -> None:
        self._stop_event.set()
```

- [ ] **Step 6: Run tests to verify they pass**

```
pytest tests/test_gpu_poller.py -v
```
Expected: 6 PASS

- [ ] **Step 7: Run full suite**

```
pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add requirements.txt gpu_poller.py tests/test_gpu_poller.py
git commit -m "feat: add GpuPoller — WMI-based GPU 3D utilization polling"
```

---

## Task 3: Add GPU Organ Voice to AudioEngine

**Files:**
- Modify: `audio_engine.py`
- Modify: `tests/test_audio_engine.py`

- [ ] **Step 1: Write failing tests**

Add to the bottom of `tests/test_audio_engine.py`:

```python
from audio_engine import _gpu_band, GPU_SILENCE_THRESHOLD


def test_gpu_band_boundaries():
    assert _gpu_band(0.0)   == 0
    assert _gpu_band(12.4)  == 0
    assert _gpu_band(12.5)  == 1
    assert _gpu_band(50.0)  == 4
    assert _gpu_band(99.9)  == 7
    assert _gpu_band(100.0) == 7


def test_gpu_organ_silent_when_gpu_vol_zero():
    """All channels except GPU active — organ should contribute nothing at gpu_vol=0."""
    state = SharedState()
    state.set_gpu_3d_percent(80.0)
    state.set_gpu_vol(0)
    state.set_volume(100)
    state.set_cpu_vol(0)
    state.set_network_vol(0)
    state.set_disk_vol(0)
    state.set_honk_vol(0)
    engine = AudioEngine(state)
    engine._on_beat(state.snapshot())  # prime organ envelope

    frames = 1024
    out = np.zeros((frames, 1), dtype=np.float32)
    engine._callback(out, frames, None, None)
    assert np.all(out == 0.0)


def test_gpu_organ_produces_audio_when_active():
    """GPU organ contributes non-zero output when gpu_3d_percent is above threshold."""
    state = SharedState()
    state.set_gpu_3d_percent(80.0)
    state.set_gpu_vol(100)
    state.set_volume(100)
    state.set_cpu_vol(0)
    state.set_network_vol(0)
    state.set_disk_vol(0)
    state.set_honk_vol(0)
    engine = AudioEngine(state)
    engine._on_beat(state.snapshot())  # prime organ envelope

    frames = 1024
    out = np.zeros((frames, 1), dtype=np.float32)
    engine._callback(out, frames, None, None)
    assert np.any(out != 0.0)


def test_gpu_organ_silent_below_threshold():
    """Organ stays silent when GPU % is below GPU_SILENCE_THRESHOLD."""
    state = SharedState()
    state.set_gpu_3d_percent(GPU_SILENCE_THRESHOLD - 1.0)
    state.set_gpu_vol(100)
    state.set_volume(100)
    state.set_cpu_vol(0)
    state.set_network_vol(0)
    state.set_disk_vol(0)
    state.set_honk_vol(0)
    engine = AudioEngine(state)
    engine._on_beat(state.snapshot())  # should NOT prime envelope

    frames = 1024
    out = np.zeros((frames, 1), dtype=np.float32)
    engine._callback(out, frames, None, None)
    assert np.all(out == 0.0)
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/test_audio_engine.py -v -k "gpu"
```
Expected: `ImportError` — `_gpu_band` not yet defined.

- [ ] **Step 3: Add GPU constants to audio_engine.py**

Add after the `# Disk tom-tom voice` block (after line ~51), before the `class AudioEngine` definition:

```python
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


def _gpu_band(gpu_percent: float) -> int:
    """Map GPU utilization % (0–100) to chord band index (0–7)."""
    return min(int(gpu_percent / 100.0 * 8), 7)
```

- [ ] **Step 4: Add GPU organ state variables to AudioEngine.__init__**

Inside `__init__`, after the `# Car horn voice` block:

```python
        # GPU organ voice
        self._gpu_band = 0
        self._gpu_organ_env = 0.0
        self._gpu_note_phases = [0.0] * 3
        self._gpu_stable_beats = 0
        self._gpu_vibrato_phase = 0.0
        self._gpu_tremolo_phase = 0.0
```

- [ ] **Step 5: Add _gpu_organ_block method**

Add after `_tom_block` and before `_make_honk_segment`:

```python
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
            # Phase accumulation: vibrato modulates instantaneous frequency
            inst_freq = f * (1.0 + vibrato)
            fund_phase_arr = self._gpu_note_phases[i] + np.cumsum(
                TWO_PI * inst_freq / SAMPLE_RATE
            )
            # Organ harmonics: harmonic n uses n × fundamental phase
            note_wave = np.zeros(frames)
            for n, w in enumerate(GPU_ORGAN_HARMONICS, start=1):
                note_wave += w * np.sin(n * fund_phase_arr)
            note_wave /= GPU_ORGAN_HARMONICS_SUM
            wave += note_wave
            self._gpu_note_phases[i] = float(fund_phase_arr[-1]) % TWO_PI

        wave /= len(chord)
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
```

- [ ] **Step 6: Add GPU organ trigger to _on_beat**

In the `_on_beat` method, append after the existing piano trigger:

```python
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
            self._gpu_organ_env = 1.0
```

- [ ] **Step 7: Add GPU voice to _callback**

In the `# Channel volumes` section, add after `honk_ch`:

```python
        gpu_ch   = snap.gpu_vol / 100.0
```

After `honk = self._honk_block(frames)`, add:

```python
        gpu_organ = self._gpu_organ_block(frames)
```

Replace the `total = (...)` block with:

```python
        total = (tach
                 + master * NET_VOICE_GAIN * net_ch * (bell + piano)
                 + master * TOM_VOICE_GAIN * disk_ch * tom
                 + master * honk_ch * honk
                 + master * GPU_VOICE_GAIN * gpu_ch * gpu_organ)
```

- [ ] **Step 8: Run GPU tests**

```
pytest tests/test_audio_engine.py -v -k "gpu"
```
Expected: 4 PASS

- [ ] **Step 9: Run full suite**

```
pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 10: Commit**

```bash
git add audio_engine.py tests/test_audio_engine.py
git commit -m "feat: add GPU organ voice — quartal chords with vibrato+tremolo wobble"
```

---

## Task 4: Wire Everything Together

**Files:**
- Modify: `main.py`
- Modify: `tray_app.py`

- [ ] **Step 1: Add GpuPoller to main.py**

Add import at the top of `main.py`:

```python
from gpu_poller import GpuPoller
```

In `main()`, after `disk_poller = DiskPoller(state)`:

```python
    gpu_poller = GpuPoller(state)
```

In `on_quit()`, after the `disk_poller.stop()` try/except block:

```python
        try:
            gpu_poller.stop()
        except Exception:
            pass
```

After `disk_poller.start()`:

```python
    gpu_poller.start()
```

- [ ] **Step 2: Add GPU volume slider to tray_app.py**

In the `channels` list inside `_open_settings`, add after `("Disk Tom", ...)`:

```python
            ("GPU Organ",           state.get_gpu_vol,      state.set_gpu_vol),
```

- [ ] **Step 3: Run full test suite**

```
pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 4: Smoke test — launch the app**

```
python main.py
```

Open Settings from the tray icon. Verify "GPU Organ" slider appears. Open Task Manager → Performance → GPU to confirm 3D % is reading. Adjust GPU Organ slider and verify the organ chord sound responds.

- [ ] **Step 5: Commit**

```bash
git add main.py tray_app.py
git commit -m "feat: wire GpuPoller into main loop and add GPU Organ volume slider"
```

- [ ] **Step 6: Push**

```bash
git push
```
