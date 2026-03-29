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


from audio_engine import _gpu_band, GPU_SILENCE_THRESHOLD


def test_gpu_band_boundaries():
    assert _gpu_band(0.0)   == 0
    assert _gpu_band(12.4)  == 0
    assert _gpu_band(12.5)  == 1
    assert _gpu_band(50.0)  == 4
    assert _gpu_band(99.9)  == 7
    assert _gpu_band(100.0) == 7


def test_gpu_organ_silent_when_gpu_vol_zero():
    """All other channels silenced — organ should contribute nothing at gpu_vol=0."""
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
