import numpy as np

from audio_engine import AudioEngine
from shared_state import SharedState


def test_pitch_formula_at_zero_cpu():
    state = SharedState()
    state.set_cpu(0.0)
    engine = AudioEngine(state)
    assert engine.target_freq() == 60.0


def test_pitch_formula_at_full_cpu():
    state = SharedState()
    state.set_cpu(100.0)
    engine = AudioEngine(state)
    assert engine.target_freq() == 300.0


def test_pitch_formula_at_half_cpu():
    state = SharedState()
    state.set_cpu(50.0)
    engine = AudioEngine(state)
    assert engine.target_freq() == 180.0


def test_amplitude_at_full_volume():
    state = SharedState()
    state.set_volume(100)
    engine = AudioEngine(state)
    assert engine.amplitude() == 1.0


def test_amplitude_at_zero_volume():
    state = SharedState()
    state.set_volume(0)
    engine = AudioEngine(state)
    assert engine.amplitude() == 0.0


def test_amplitude_at_half_volume():
    state = SharedState()
    state.set_volume(50)
    engine = AudioEngine(state)
    assert abs(engine.amplitude() - 0.5) < 0.001


def test_callback_phase_continuity():
    """Verify no discontinuity at block boundaries (no audible clicks)."""
    state = SharedState()
    state.set_cpu(50.0)   # 180 Hz
    state.set_volume(100)
    engine = AudioEngine(state)

    frames = 1024
    # First block
    out1 = np.zeros((frames, 1), dtype=np.float32)
    engine._callback(out1, frames, None, None)

    # Second block — must be continuous with first
    out2 = np.zeros((frames, 1), dtype=np.float32)
    engine._callback(out2, frames, None, None)

    # Last sample of block 1 and first sample of block 2 should be close
    # (within one sample's worth of sine movement at 180 Hz)
    max_step = 2 * np.pi * 180.0 / 44100.0  # max change in one sample
    actual_step = abs(float(out2[0, 0]) - float(out1[-1, 0]))
    assert actual_step < max_step * 2, (
        f"Discontinuity at block boundary: {actual_step:.4f} > {max_step * 2:.4f}"
    )
