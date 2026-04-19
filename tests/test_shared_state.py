import threading
from shared_state import SharedState


def test_default_values():
    state = SharedState()
    assert state.get_cpu() == 0.0
    assert state.get_volume() == 2


def test_set_and_get_cpu():
    state = SharedState()
    state.set_cpu(73.5)
    assert state.get_cpu() == 73.5


def test_set_and_get_volume():
    state = SharedState()
    state.set_volume(80)
    assert state.get_volume() == 80


def test_concurrent_cpu_writes_do_not_corrupt():
    state = SharedState()
    errors = []

    def writer(val):
        try:
            for _ in range(1000):
                state.set_cpu(float(val))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert 0.0 <= state.get_cpu() <= 4.0  # range(5) gives writers values 0.0–4.0


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
