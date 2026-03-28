import threading
from shared_state import SharedState


def test_default_values():
    state = SharedState()
    assert state.get_cpu() == 0.0
    assert state.get_volume() == 50


def test_set_and_get_cpu():
    state = SharedState()
    state.set_cpu(73.5)
    assert state.get_cpu() == 73.5


def test_set_and_get_volume():
    state = SharedState()
    state.set_volume(80)
    assert state.get_volume() == 80


def test_concurrent_writes_do_not_corrupt():
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
    assert 0.0 <= state.get_cpu() <= 4.0  # one of the writer values
