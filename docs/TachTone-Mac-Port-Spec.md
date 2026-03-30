# TachTone — macOS Port Specification

## Recommended Stack: Swift

For a polished, distributable macOS app, **Swift is the recommended implementation language.** It provides:

- Native `NSStatusItem` for a proper menu bar presence (no Dock icon)
- First-class `IOKit` access for GPU utilization metrics
- `AVAudioEngine` / `CoreAudio` for low-latency audio synthesis
- A native settings UI that looks at home on macOS
- A signable, notarizable `.app` bundle distributable via GitHub — no App Store required

The existing Windows version is written in Python and works well as a reference for behavior, audio math, and architecture. This spec describes *what* TachTone does, not *how* the Windows version did it in Python. The implementor is free to choose the tools and libraries that best fit Swift and macOS.

---

## What TachTone Does

TachTone runs silently in the macOS menu bar and synthesizes a continuous audio soundscape driven by live system activity. There is no main window — only a menu bar icon, a settings panel, and sound.

The core metaphor: **your Mac sounds like a car engine.** CPU load drives the RPM. Everything else layers on top.

---

## Architecture

Six concurrent components share one thread-safe state object:

```
App Entry Point
 ├── SharedState          — thread-safe container for all live metrics and settings
 ├── CpuPoller            — samples CPU load and context-switch rate every 500ms
 ├── NetworkPoller        — samples bytes in/out every 500ms
 ├── DiskPoller           — samples total disk read+write bytes/sec every 500ms
 ├── GpuPoller            — samples GPU 3D engine utilization % every 500ms
 ├── HonkListener         — listens on UDP 127.0.0.1:9876 for Claude Code signals
 └── AudioEngine          — real-time audio callback, mixes all voices every ~23ms
```

The menu bar UI runs on the main thread. All pollers run on background threads. The audio engine runs a real-time callback driven by the audio hardware — this callback must never block.

---

## SharedState

All live data lives in one shared, thread-safe container. Every poller writes into it; the audio engine reads an atomic snapshot at the start of each audio callback.

| Field | Type | Default | Description |
|---|---|---|---|
| `cpu_percent` | float | 0.0 | Current CPU utilization, 0–100 |
| `ctx_rate` | float | 0.0 | Context switches per second |
| `net_recv_rate` | float | 0.0 | Bytes/sec received |
| `net_send_rate` | float | 0.0 | Bytes/sec sent |
| `disk_rate` | float | 0.0 | Bytes/sec total disk I/O (reads + writes) |
| `gpu_3d_percent` | float | 0.0 | GPU 3D engine utilization, 0–100 |
| `volume` | int | 50 | Master volume, 0–100 |
| `cpu_vol` | int | 80 | CPU tone channel, 0–100 |
| `interrupts_vol` | int | 12 | Interrupt vibrato channel, 0–100 |
| `network_vol` | int | 50 | Network bell/piano channel, 0–100 |
| `disk_vol` | int | 50 | Disk tom-tom channel, 0–100 |
| `gpu_vol` | int | 50 | GPU organ channel, 0–100 |
| `honk_vol` | int | 100 | Horn channel, 0–100 |
| `honk` | bool | false | One-shot flag: trigger a standard double-honk |
| `impatient_honk` | bool | false | One-shot flag: trigger the impatient horn sequence |
| `impatient_honking_enabled` | bool | true | Whether the impatient timer fires |

The audio engine reads these as a single consistent snapshot. One-shot flags (`honk`, `impatient_honk`) are cleared by the audio engine immediately after it acts on them.

---

## System Pollers

Each poller samples its metric every **500ms** and writes into SharedState.

### CPU Poller
- **CPU load**: overall system CPU utilization as a percentage (0–100)
- **Context-switch rate**: number of context switches per second, computed as `(delta_count / elapsed_seconds)` between samples

### Network Poller
- **Bytes received per second** and **bytes sent per second**
- Monitor the primary Wi-Fi adapter (typically `en0` on macOS). If unavailable, sum all adapters.
- Make the adapter name configurable via environment variable `TACHTONE_NET_ADAPTER` (default `"en0"`)
- Clamp values to 0 (counter wraps or resets should not produce negative rates)

### Disk Poller
- **Total disk I/O rate**: `(read_bytes_delta + write_bytes_delta) / elapsed_seconds`
- Sum across all physical disks

### GPU Poller
- **GPU 3D engine utilization %** (0–100)
- On macOS, query via IOKit — specifically the `IOAccelerator` class, looking for 3D engine utilization in the `PerformanceStatistics` dictionary
- On Apple Silicon (M-series), the integrated GPU reports differently than Intel + discrete GPU Macs. Handle both gracefully.
- If no GPU data is available, default to 0.0. The organ voice will simply stay silent. Never crash on missing GPU data.

### Honk Listener
- Binds a **UDP socket** on `127.0.0.1` port `9876` (overridable via `TACHTONE_HONK_PORT`)
- Receives datagrams from Claude Code hooks and updates SharedState accordingly:

| Datagram received | Action |
|---|---|
| `"need attention"` | Trigger standard honk + start 30s impatient timer |
| `"got attention"` | Cancel all timers |
| `"claude task complete"` | Cancel all timers + trigger standard honk |
| `"pre_tool_use"` | Cancel impatient timer + start 8s approval timer |
| `"post_tool_use"` | Cancel approval timer |

**Impatient timer**: if `"need attention"` is received and the user does not respond within 30 seconds, fire the impatient horn sequence.

**Approval timer**: if `"pre_tool_use"` fires but `"post_tool_use"` does not arrive within 8 seconds, Claude is assumed to be waiting at a tool-approval dialog — fire a standard honk and restart the impatient timer.

---

## Audio Engine

- **Sample rate**: 44,100 Hz
- **Block size**: 1,024 frames per callback (~23ms)
- **Output**: mono, 32-bit float, values clamped to [-1.0, 1.0]

The callback fires approximately every 23ms. At the top of each callback, take a snapshot of SharedState. All synthesis for that block uses this snapshot — no further reads from shared state.

### Voice Mix

```
output = clip(
    master * cpu_ch   * engine_voice
  + master * 0.27     * net_ch  * (bell + piano)
  + master * 0.35     * disk_ch * tom
  + master * honk_ch  * honk
  + master * 0.30     * gpu_ch  * organ
, -1.0, 1.0)
```

Where `master = volume / 100` and `*_ch = channel_vol / 100`.

---

## Voice Specifications

### Voice 1: CPU Engine Tone

A 4-cylinder engine simulation. The pitch tracks CPU load in real time.

**RPM mapping:**
- 0% CPU → 700 RPM
- 100% CPU → 7,000 RPM
- Crankshaft fundamental frequency (Hz) = RPM / 60

**Frequency smoothing**: apply a first-order low-pass filter with α = 0.02 per block. The engine cannot instantly snap to a new RPM — it has inertia.

**Harmonic stack** (4-cylinder profile):

| Harmonic | Weight |
|---|---|
| 1st | 0.30 |
| 2nd | 1.00 |
| 3rd | 0.45 |
| 4th | 0.80 |
| 5th | 0.25 |
| 6th | 0.55 |
| 7th | 0.15 |
| 8th | 0.35 |

Even harmonics are louder — they represent the firing pulses of a 4-cylinder. Normalize the sum before applying gain.

**Amplitude modulation (idle chug)**:
- AM frequency = 2× crankshaft frequency (4-cylinder fires twice per crank revolution)
- AM depth = `0.40 × max(0, 1 - cpu_pct / 67)`
- At idle: full loping chug. Above 67% CPU: no chug (engine is screaming)

**Mechanical noise**: add white noise at amplitude 0.004 each block.

**RPM instability** (context-switch vibrato):
- A 7 Hz LFO modulates the crankshaft frequency
- Depth = `(ctx_rate / 50,000) × current_freq × 0.05 × (interrupts_vol / 100)`
- At high context-switch rates the engine "hunts" — it sounds stressed and unstable

**Phase continuity**: accumulate the fundamental phase continuously across blocks. Never reset phase between blocks — this prevents clicks.

---

### Voice 2: Network Bell and Piano

Two beat-triggered melodic voices. Bell = incoming traffic. Piano = outgoing traffic.

**Tempo**: 80 BPM. One beat = `44100 × 60 / 80 = 33,075 samples`.

**On each beat**:
- If received rate > 5,000 bytes/sec: trigger bell at a pitch selected from 8 notes
- If sent rate > 5,000 bytes/sec: trigger piano at a pitch selected from 8 notes
- Band selection: `min(floor(rate / 500,000 × 8), 7)`

**Note frequencies** (C major scale, C5–C6):
`523.25, 587.33, 659.25, 698.46, 783.99, 880.00, 987.77, 1046.50` Hz

**Bell timbre** (incoming): fundamental + 2nd harmonic at 25% + 3rd harmonic at 10%. Decay time constant: 50ms. Normalize by 1.35.

**Piano timbre** (outgoing): fundamental + harmonics at 60%, 35%, 15%. Decay time constant: 30ms. Normalize by 2.10.

Both voices reset their amplitude envelope to 1.0 on each new trigger. Phase accumulates continuously.

---

### Voice 3: Disk Tom-Tom

A pitched percussion voice triggered by disk I/O.

**Tempo**: 16th notes = beat interval / 4 (four times the network beat rate).

**On each 16th note**:
- If disk rate > 100,000 bytes/sec: strike a tom
- Pitch band: `min(floor(disk_rate / 10,000,000 × 8), 7)`
- Tom frequencies (Hz): `80, 100, 120, 140, 165, 190, 215, 250`

**Tom timbre**:
- Sine wave with amplitude decay time constant: 70ms
- Pitch sweep: starts 25 Hz above target, decays to target over 25ms (the "thwack" of a drum hit)
- Phase accumulation must account for the time-varying frequency

---

### Voice 4: GPU Organ

A haunting quartal-chord organ driven by GPU utilization.

**Silence threshold**: below 5% GPU, organ stays silent.

**Chord selection**: 8 bands of 3-note quartal chords (notes stacked in perfect 4ths = 5 semitones):

| Band | GPU % | Notes | Frequencies (Hz) |
|---|---|---|---|
| 0 | 0–12.5% | C4 + F4 + Bb4 | 261.63, 349.23, 466.16 |
| 1 | 12.5–25% | D4 + G4 + C5 | 293.66, 392.00, 523.25 |
| 2 | 25–37.5% | E4 + A4 + D5 | 329.63, 440.00, 587.33 |
| 3 | 37.5–50% | F4 + Bb4 + Eb5 | 349.23, 466.16, 622.25 |
| 4 | 50–62.5% | G4 + C5 + F5 | 392.00, 523.25, 698.46 |
| 5 | 62.5–75% | A4 + D5 + G5 | 440.00, 587.33, 783.99 |
| 6 | 75–87.5% | B4 + E5 + A5 | 493.88, 659.25, 880.00 |
| 7 | 87.5–100% | C5 + F5 + Bb5 | 523.25, 698.46, 932.33 |

**Band transitions**: when GPU load changes, step exactly one band per beat toward the target. Never jump more than one chord at a time — this creates smooth melodic motion.

**Beat voicings**: on each beat, randomly select one of these note subsets to play:
- All three notes (root + 4th + top)
- Root + 4th
- 4th + top
- Root + top (open voicing)

This causes the chord to breathe rather than drone.

**Organ timbre**: harmonics 1–4 at weights `1.0, 0.7, 0.5, 0.3`. Normalize by sum.

**Wobble** (builds gradually after a chord stabilizes):
- Vibrato: 4.5 Hz LFO, ±0.4% frequency modulation
- Tremolo: 3.1 Hz LFO, ±25% amplitude modulation
- Both ramp from zero to full depth over 4 stable beats

**Envelope**: each beat trigger resets amplitude to 1.0 with a 1.8-second decay. Chords overlap and sustain.

---

### Voice 5: Car Horn

A two-tone horn: **G4 (392 Hz) + B4 (494 Hz)**.

**Standard honk** (attention needed or task complete):
- Two 180ms blasts with a 90ms gap between them
- Each blast: 10ms attack, 25ms release

**Impatient honk** (user ignored Claude for 30+ seconds):
- 3–4 quick honks (cluster)
- 350ms pause
- One long lean: 4.5–5.5 seconds
- 350ms pause
- 3–4 quick honks (cluster)
- 350ms pause
- One medium lean: 1.8–2.2 seconds
- Cluster size and lean duration are randomized each time

Pre-render the entire sequence as a buffer at trigger time. Stream from the buffer each audio callback until exhausted.

---

## Menu Bar UI

- App lives exclusively in the menu bar. No Dock icon (`LSUIElement = true` in `Info.plist`).
- Menu bar icon: a tachometer gauge — dark circular background, orange arc sweep, tick marks, white needle, blue musical note, orange speaker. Drawn programmatically, not loaded from an asset file.
- Right-click menu:
  - **Settings** — opens the settings panel
  - **Quit** — stops all components and exits

---

## Settings Panel

A simple floating panel (not a full window). All controls are live — they update the audio immediately with no Apply button.

**Volume sliders** (0–100 each):
- Master Volume
- *(visual separator)*
- CPU Tone
- Interrupts (vibrato)
- Network Bell/Piano
- Disk Tom
- GPU Organ
- Honk Honk

**Toggle**:
- "Include impatient honking" checkbox (default: on)

Settings are not persisted between launches. All values reset to defaults on each app start.

---

## Claude Code Integration

### How it works

Claude Code fires lifecycle hooks (shell commands) at key moments. These hooks send a short UDP datagram to TachTone's listener. TachTone reacts with sound.

### Hook configuration

Add this to `~/.claude/settings.json` on the Mac:

```json
{
  "hooks": {
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 -c \"import socket; socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b'need attention', ('127.0.0.1', 9876))\""
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 -c \"import socket; socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b'claude task complete', ('127.0.0.1', 9876))\""
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 -c \"import socket; socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b'pre_tool_use', ('127.0.0.1', 9876))\""
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 -c \"import socket; socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b'post_tool_use', ('127.0.0.1', 9876))\""
          }
        ]
      }
    ]
  }
}
```

The hook scripts use `python3` (always available on macOS) purely to send a UDP packet — this is a one-liner with no dependencies. The TachTone app itself does not need to be Python.

---

## Audio Constants Reference

These values define the character of every sound. Do not change them without intent — they were tuned carefully on the Windows version.

| Constant | Value | What it controls |
|---|---|---|
| Sample rate | 44,100 Hz | Audio fidelity |
| Block size | 1,024 frames | Callback latency (~23ms) |
| Frequency smoothing α | 0.02 per block | Engine inertia |
| LFO rate | 7.0 Hz | Context-switch wobble speed |
| Max context rate | 50,000 ctx/sec | Rate that saturates vibrato |
| Engine idle RPM | 700 | Pitch at 0% CPU |
| Engine max RPM | 7,000 | Pitch at 100% CPU |
| AM chug depth | 0.40 | Idle lope intensity |
| AM chug cutoff | 67% CPU | Above this, chug disappears |
| Noise floor | 0.004 amplitude | Mechanical texture |
| Tempo | 80 BPM | Network and GPU beat clock |
| Net max rate | 500,000 bytes/sec | Saturates note selection |
| Net silence threshold | 5,000 bytes/sec | Below this: no note |
| Disk max rate | 10,000,000 bytes/sec | Saturates tom pitch |
| Disk silence threshold | 100,000 bytes/sec | Below this: no tom hit |
| GPU silence threshold | 5% | Below this: organ silent |
| GPU organ decay | 1.8 sec | Chord sustain length |
| GPU wobble beats | 4 | Beats before full vibrato |
| Vibrato rate | 4.5 Hz | Organ pitch wobble speed |
| Tremolo rate | 3.1 Hz | Organ amplitude wobble speed |
| Horn freq 1 | 392 Hz (G4) | Low horn tone |
| Horn freq 2 | 494 Hz (B4) | High horn tone |
| Honk duration | 180ms | Length of one blast |
| Honk gap | 90ms | Silence between double-honk |
| Impatient delay | 30 sec | Wait before impatient horn |
| Approval wait | 8 sec | Wait for tool approval |

---

## Distribution

Target: a `.dmg` containing a signed `.app` bundle, posted as a GitHub release asset — same model as the Windows `.exe`.

- No App Store submission required
- Signing + notarization requires an Apple Developer account ($99/year) and eliminates Gatekeeper warnings for end users
- Without signing, users can still run the app via right-click → Open (one-time step)
- Set `LSUIElement = true` in `Info.plist` so the app appears only in the menu bar, not the Dock
