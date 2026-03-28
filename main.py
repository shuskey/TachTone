from shared_state import SharedState
from cpu_poller import CpuPoller
from audio_engine import AudioEngine
from tray_app import TrayApp


def main():
    state = SharedState()

    poller = CpuPoller(state)
    engine = AudioEngine(state)

    def on_quit():
        poller.stop()
        engine.stop()

    tray = TrayApp(state, on_quit=on_quit)

    poller.start()
    engine.start()
    tray.run()  # blocks on main thread until quit


if __name__ == "__main__":
    main()
