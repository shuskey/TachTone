# GPU Organ Channel — Design Spec
**Date:** 2026-03-29
**Status:** Approved

---

## Overview

Add a GPU 3D load monitoring channel to TachTone. GPU utilization is mapped to one of eight quartal chords that sustain and overlap like an organ pad, with layered vibrato and tremolo wobble emerging during periods of stable load.

---

## GPU Polling

A new `GpuPoller` thread mirrors `CpuPoller` in structure. It polls every 500ms using the `wmi` library, querying `Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine` and filtering for entries whose `Name` contains `"engtype_3D"`. The utilization values for all matching entries are summed to produce a single `gpu_3d_percent` float (0–100), matching what Windows Task Manager displays.

`gpu_3d_percent` and a new `gpu_vol` channel (int 0–100, default 50) are added to `SharedState`. `GpuPoller` is started in `main.py` alongside `CpuPoller`.

**New dependency:** `wmi` added to `requirements.txt`.

---

## Quartal Chord System

Eight quartal chords, each built from three notes stacked in perfect 4ths (5 semitones), rooted on successive C major scale degrees:

| Band | GPU %       | Root | Chord tones         |
|------|-------------|------|---------------------|
| 0    | 0–12.5%     | C4   | C4 + F4 + Bb4       |
| 1    | 12.5–25%    | D4   | D4 + G4 + C5        |
| 2    | 25–37.5%    | E4   | E4 + A4 + D5        |
| 3    | 37.5–50%    | F4   | F4 + Bb4 + Eb5      |
| 4    | 50–62.5%    | G4   | G4 + C5 + F5        |
| 5    | 62.5–75%    | A4   | A4 + D5 + G5        |
| 6    | 75–87.5%    | B4   | B4 + E5 + A5        |
| 7    | 87.5–100%   | C5   | C5 + F5 + Bb5       |

Each note uses organ-style harmonics: partials 1–4 at weights 1.0 / 0.7 / 0.5 / 0.3. The chord is triggered on the network beat clock (quarter notes, 80 BPM ≈ 0.75s per beat). Decay constant is ~1.8 seconds, so successive chords overlap and wash together as a pad.

Band changes move to the adjacent row (one step up or down), so load shifts produce smooth melodic motion rather than jumps.

---

## Wobble — Vibrato + Tremolo

A `_gpu_stable_beats` counter increments each beat the GPU remains in the same band, and resets to zero on any band change. Wobble depth ramps from 0 to full over 4 stable beats (depth = `min(_gpu_stable_beats / 4, 1.0)`), so chord changes feel clean and shimmer only emerges during sustained load.

Two independent LFOs run continuously on the organ voice, scaled by the wobble depth:

- **Vibrato:** 4.5 Hz — modulates each note's frequency ±0.4% (≈ ±8 cents at C4), applied via per-sample phase accumulation.
- **Tremolo:** 3.1 Hz — modulates amplitude ±25%.

The non-integer ratio (4.5 vs 3.1 Hz) causes the two LFOs to drift in and out of phase, producing an organic beating pattern. Both LFOs run always; only their depth is gated, avoiding clicks on onset or offset.

---

## Architecture Changes

| File | Change |
|------|--------|
| `requirements.txt` | Add `wmi` |
| `shared_state.py` | Add `gpu_3d_percent`, `gpu_vol` fields and accessors |
| `gpu_poller.py` | New file — WMI-based GPU polling thread |
| `audio_engine.py` | Add GPU organ voice (`_gpu_organ_block`), beat trigger, wobble state |
| `tray_app.py` | Add GPU volume slider to settings UI |
| `main.py` | Instantiate and start `GpuPoller` |

---

## Constants (proposed)

```python
GPU_ORGAN_DECAY    = 1.8      # seconds
GPU_VOICE_GAIN     = 0.30     # amplitude
GPU_VIBRATO_RATE   = 4.5      # Hz
GPU_TREMOLO_RATE   = 3.1      # Hz
GPU_VIBRATO_DEPTH  = 0.004    # ±0.4% of frequency
GPU_TREMOLO_DEPTH  = 0.25     # ±25% amplitude
GPU_WOBBLE_BEATS   = 4        # beats until full wobble
```

---

## Testing

- Unit test `GpuPoller` by mocking the WMI query to return known values and asserting `SharedState.gpu_3d_percent` is set correctly.
- Unit test band→chord mapping with boundary values (0%, 12.4%, 12.5%, 100%).
- Audio engine tests mock `SharedState.snapshot()` and verify `_gpu_organ_block` returns non-zero output when `gpu_3d_percent > 0` and zero when `gpu_vol = 0`.
