# TachTone

A Windows system tray app that turns CPU usage into sound.

## What It Does

Synthesizes a continuous sine wave whose pitch tracks CPU load:
- 0% CPU → 60 Hz (idle rumble)
- 100% CPU → 300 Hz (full rev)

Volume is the only user control. At volume 0 the tone is silent but still running.

## Architecture

Three concurrent components:
- `CpuPoller` — polls `psutil.cpu_percent()` every 500ms
- `AudioEngine` — `sounddevice` callback stream, morphs pitch each block
- `TrayApp` — `pystray` tray icon, opens Tkinter settings in its own thread

Shared state (`cpu_percent`, `volume`) lives in `SharedState` with a `threading.Lock`.

## Running

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
python main.py
```

## Testing

```bash
pytest tests/ -v
```

## Key Files

| File | Role |
|---|---|
| `main.py` | Entry point |
| `shared_state.py` | Thread-safe state container |
| `cpu_poller.py` | CPU polling thread |
| `audio_engine.py` | Audio synthesis thread |
| `tray_app.py` | System tray + settings UI |
