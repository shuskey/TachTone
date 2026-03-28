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
