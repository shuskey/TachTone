# TachTone — Design Spec

**Date:** 2026-03-27
**Status:** Approved

## Overview

TachTone is a Windows system monitor that turns CPU usage into sound. It lives in the system tray and continuously synthesizes a low-frequency tone whose pitch tracks CPU load — like an engine revving up and down. Volume is the only user-facing control; at volume 0 the tone is silent but the engine is still running.

---

## Architecture

Three concurrent components share two pieces of state (`cpu_percent`, `volume`):

```
┌─────────────────┐     shared state      ┌─────────────────┐
│   CpuPoller     │ ──── cpu_percent ────▶ │  AudioEngine    │
│  (thread)       │                        │  (thread)       │
└─────────────────┘                        └─────────────────┘
                                                    ▲
┌─────────────────┐     shared state               │
│  SystemTray     │ ──── volume (0–100) ───────────┘
│  (main thread)  │
│  + Tkinter      │
│    config popup │
└─────────────────┘
```

### CpuPoller (thread)
- Polls `psutil.cpu_percent()` every 500ms
- Writes result to shared `cpu_percent` float (protected by `threading.Lock`)

### AudioEngine (thread)
- Runs a continuous sine wave output stream via `sounddevice` (callback-based, non-blocking)
- Reads `cpu_percent` to compute target pitch
- Reads `volume` to scale amplitude
- Smoothly interpolates pitch each callback to avoid clicks: `current_freq += (target_freq - current_freq) * 0.05`

### SystemTray (main thread)
- `pystray` icon in the Windows taskbar
- Tray icon: simple generated image via `Pillow` (no external image file)
- Right-click menu: **Settings**, **Quit**
- **Settings** launches a Tkinter window in a dedicated thread (Tkinter must own its thread; it cannot run in the pystray callback directly); changes apply immediately to shared `volume`
- **Quit** stops both threads cleanly and exits

### Shared State (`shared_state.py`)
- Two values: `cpu_percent` (float) and `volume` (int, 0–100)
- Protected by a single `threading.Lock`
- Default volume: 50

---

## Audio Design

| Property | Value |
|---|---|
| Waveform | Sine wave |
| Idle frequency (0% CPU) | 60 Hz |
| Max frequency (100% CPU) | 300 Hz |
| Pitch formula | `freq = 60 + (cpu_percent / 100) * 240` |
| Sample rate | 44100 Hz |
| Block size | 1024 samples (~43 callbacks/sec) |
| Pitch smoothing | Exponential interpolation (factor 0.05 per callback) |
| Amplitude | `volume / 100.0` |
| At volume 0 | Silent but running — "waiting" state |
| Phase continuity | `phase` carried across callbacks to avoid discontinuities |

---

## File Structure

```
TachTone/
├── main.py              # Entry point — wires up threads, starts tray
├── cpu_poller.py        # CpuPoller thread
├── audio_engine.py      # AudioEngine thread + sine wave synthesis
├── tray_app.py          # SystemTray (pystray) + Settings popup (Tkinter)
├── shared_state.py      # Shared cpu_percent + volume with threading.Lock
├── requirements.txt     # psutil, sounddevice, numpy, pystray, Pillow
└── CLAUDE.md            # Project context for Claude Code
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `psutil` | CPU usage polling |
| `sounddevice` | Real-time audio output stream |
| `numpy` | Sine wave generation |
| `pystray` | Windows system tray icon |
| `Pillow` | Generate tray icon image |

---

## Out of Scope (MVP)

- GPU, RAM, disk, network metrics
- Multiple waveforms or harmonic richness
- Persistent settings (config file)
- Auto-start on Windows login
- Packaging as `.exe` (pyinstaller)
- Threshold-based silence
