from shared_state import SharedState
from cpu_poller import CpuPoller
from network_poller import NetworkPoller
from disk_poller import DiskPoller
from honk_listener import HonkListener
from audio_engine import AudioEngine
from tray_app import TrayApp


def main():
    state = SharedState()

    poller = CpuPoller(state)
    net_poller = NetworkPoller(state)
    disk_poller = DiskPoller(state)
    honk_listener = HonkListener(state)
    engine = AudioEngine(state)

    def on_quit():
        try:
            poller.stop()
        except Exception:
            pass
        try:
            net_poller.stop()
        except Exception:
            pass
        try:
            disk_poller.stop()
        except Exception:
            pass
        try:
            honk_listener.stop()
        except Exception:
            pass
        finally:
            engine.stop()

    tray = TrayApp(state, on_quit=on_quit)

    poller.start()
    net_poller.start()
    disk_poller.start()
    honk_listener.start()
    engine.start()
    tray.run()  # blocks on main thread until quit


if __name__ == "__main__":
    main()
