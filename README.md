# TachTone

<img src="made-with-claude.png" alt="Made with Claude" width="200"/>

> Your PC sounds like an engine. CPU load drives the RPM.

[![GitHub release](https://img.shields.io/github/v/release/shuskey/TachTone)](https://github.com/shuskey/TachTone/releases/latest)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-blue)

A system tray app for Windows and Linux (tested on [Omarchy](https://omarchy.org/)/Hyprland) that synthesizes a continuous engine tone whose pitch tracks CPU usage in real time — idle hum at low load, full rev at 100%. Disk, network, and context-switch activity layer in percussion, arpeggios, and vibrato. Oh, and when Claude Code needs your attention, you'll hear it honking at you!

---

## What You Hear

| Activity | Sound |
|---|---|
| CPU load | Engine RPM (700–7000 RPM harmonic stack) |
| Context switches | Vibrato / RPM instability |
| Disk I/O | Tom-tom hits (pitch = activity level) |
| Network traffic | Bell (incoming) + piano (outgoing) arpeggios |
| Claude needs attention | Two-tone car horn honk (Claude Code finished / waiting for you) |
| Claude ignored too long | Impatient horn (Claude asked for input and you haven't responded) |

## Install

### Windows

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
python main.py
```

Requires Python 3.10+.

### Linux / Omarchy

```bash
# System packages the venv can't provide on its own:
#   tk                        — Settings window (Tkinter)
#   python-gobject            — tray icon backend (PyGObject / gi)
#   libayatana-appindicator   — tray icon protocol
omarchy pkg add tk

python -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

`--system-site-packages` is required so the venv can see the system-installed
`python-gobject`, which `pystray` needs for its Linux tray backend. GPU load
is read via `nvidia-smi` (NVIDIA) or `/sys/class/drm/*/device/gpu_busy_percent`
(AMD); if neither is present the GPU organ voice just stays silent.

To run TachTone automatically on login, see [Autostart on Linux](#autostart-on-linux-systemd) below.

## System Tray

TachTone runs silently in the system tray.

**Windows:** look for the hidden icons arrow (**^**) in the bottom-right corner
of the taskbar, then locate the TachTone icon.

**Omarchy:** the tray icon appears in the `omarchy.tray` bar widget (enabled
by default).

**Right-click** the icon for the context menu:
- **Settings** — open the volume mixer
- **Quit** — stop TachTone

## Settings

Right-click the tray icon → **Settings** to mix per-channel volumes:

- Master, CPU Tone, Interrupts (vibrato), Network Bell/Piano, Disk Tom, Honk

## Claude Code Integration

TachTone hooks into [Claude Code](https://claude.ai/code) so the horn honks whenever Claude needs your attention — end of response, tool permission prompt, or any choice dialog.

Add this to `~/.claude/settings.json` (Windows uses `python`; on Linux/Omarchy, swap in `python3`):

```json
{
  "hooks": {
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "async": true,
      "command": "python -c \"import socket,os,sys; sys.stdin.read(); s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.sendto(b'got attention',('127.0.0.1',int(os.environ.get('TACHTONE_HONK_PORT',9876))))\"" }] }],
    "Stop": [{ "hooks": [{ "type": "command", "async": true,
      "command": "python -c \"import socket,os,sys; sys.stdin.read(); s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.sendto(b'claude task complete',('127.0.0.1',int(os.environ.get('TACHTONE_HONK_PORT',9876))))\"" }] }],
    "Notification": [{ "hooks": [{ "type": "command", "async": true,
      "command": "python -c \"import socket,os,sys; sys.stdin.read(); s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.sendto(b'need attention',('127.0.0.1',int(os.environ.get('TACHTONE_HONK_PORT',9876))))\"" }] }],
    "PreToolUse": [{ "hooks": [{ "type": "command", "async": true,
      "command": "python -c \"import socket,os,sys; sys.stdin.read(); s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.sendto(b'pre_tool_use',('127.0.0.1',int(os.environ.get('TACHTONE_HONK_PORT',9876))))\"" }] }],
    "PostToolUse": [{ "hooks": [{ "type": "command", "async": true,
      "command": "python -c \"import socket,os,sys; sys.stdin.read(); s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.sendto(b'post_tool_use',('127.0.0.1',int(os.environ.get('TACHTONE_HONK_PORT',9876))))\"" }] }]
  }
}
```

The `PreToolUse` / `PostToolUse` pair is a workaround for the absence of a dedicated tool-approval hook. When `PreToolUse` fires, TachTone starts an 8-second timer. If `PostToolUse` arrives within 8 seconds the tool was auto-approved and the timer is cancelled silently. If the timer expires, Claude is assumed to be waiting at an approval dialog and the impatient honk fires.

TachTone must be running. Set `TACHTONE_HONK_PORT` if you changed the default port (9876).

## Autostart on Linux (systemd)

A ready-made systemd user unit is provided at
[`installer/tachtone.service`](installer/tachtone.service). It assumes the
repo is cloned to `~/Projects/TachTone` — edit the `ExecStart`/`WorkingDirectory`
paths first if yours lives elsewhere.

```bash
mkdir -p ~/.config/systemd/user
cp installer/tachtone.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now tachtone.service
```

Check it's running and listen for the engine:

```bash
systemctl --user status tachtone.service
journalctl --user -u tachtone.service -f
```

## Stack

`psutil` · `sounddevice` · `numpy` · `pystray` · `Pillow`

## Tests

```bash
pytest tests/ -v
```
