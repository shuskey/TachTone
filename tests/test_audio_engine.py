import numpy as np

from audio_engine import AudioEngine, ENGINE_IDLE_RPM, ENGINE_MAX_RPM
from shared_state import SharedState


def test_pitch_formula_at_zero_cpu():
    state = SharedState()
    state.set_cpu(0.0)
    engine = AudioEngine(state)
    assert engine.target_freq() == ENGINE_IDLE_RPM / 60.0


def test_pitch_formula_at_full_cpu():
    state = SharedState()
    state.set_cpu(100.0)
    engine = AudioEngine(state)
    assert engine.target_freq() == ENGINE_MAX_RPM / 60.0


def test_pitch_formula_at_half_cpu():
    state = SharedState()
    state.set_cpu(50.0)
    engine = AudioEngine(state)
    mid_rpm = ENGINE_IDLE_RPM + 0.5 * (ENGINE_MAX_RPM - ENGINE_IDLE_RPM)
    assert engine.target_freq() == mid_rpm / 60.0


def test_volume_zero_produces_silence():
    state = SharedState()
    state.set_cpu(50.0)
    state.set_volume(0)
    engine = AudioEngine(state)

    frames = 1024
    out = np.zeros((frames, 1), dtype=np.float32)
    engine._callback(out, frames, None, None)

    assert np.all(out == 0.0), "Expected silence at volume 0"


def test_volume_nonzero_produces_audio():
    state = SharedState()
    state.set_cpu(50.0)
    state.set_volume(100)
    engine = AudioEngine(state)

    frames = 1024
    out = np.zeros((frames, 1), dtype=np.float32)
    engine._callback(out, frames, None, None)

    assert np.any(out != 0.0), "Expected non-silent output at volume 100"


def test_callback_phase_continuity():
    """Verify no discontinuity at block boundaries (no audible clicks)."""
    state = SharedState()
    state.set_cpu(50.0)   # mid RPM
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
    # (within one sample's worth of sine movement at the fundamental frequency)
    from audio_engine import ENGINE_IDLE_RPM, ENGINE_MAX_RPM, SAMPLE_RATE
    mid_rpm = ENGINE_IDLE_RPM + 0.5 * (ENGINE_MAX_RPM - ENGINE_IDLE_RPM)
    fund_freq = mid_rpm / 60.0
    max_step = 2 * np.pi * fund_freq / SAMPLE_RATE
    actual_step = abs(float(out2[0, 0]) - float(out1[-1, 0]))
    assert actual_step < max_step * 2, (
        f"Discontinuity at block boundary: {actual_step:.4f} > {max_step * 2:.4f}"
    )
