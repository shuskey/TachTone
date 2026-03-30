# TachTone

<img src="made-with-claude.png" alt="Made with Claude" width="200"/>

> Your PC sounds like an engine. CPU load drives the RPM.

[![GitHub release](https://img.shields.io/github/v/release/shuskey/TachTone)](https://github.com/shuskey/TachTone/releases/latest)
![Platform](https://img.shields.io/badge/platform-Windows-blue)

A Windows system tray app that synthesizes a continuous engine tone whose pitch tracks CPU usage in real time — idle hum at low load, full rev at 100%. Disk, network, and context-switch activity layer in percussion, arpeggios, and vibrato. Oh, and when Claude Code needs your attention, you'll hear it honking at you!

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

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Requires Python 3.10+ and Windows (system tray + audio).

## System Tray

TachTone runs silently in the Windows system tray. To find it:

1. Look for the hidden icons arrow (**^**) in the bottom-right corner of the taskbar.
2. Click it to expand the tray, then locate the TachTone icon.
3. **Right-click** the icon for the context menu:
   - **Settings** — open the volume mixer
   - **Quit** — stop TachTone

## Settings

Right-click the tray icon → **Settings** to mix per-channel volumes:

- Master, CPU Tone, Interrupts (vibrato), Network Bell/Piano, Disk Tom, Honk

## Claude Code Integration

TachTone hooks into [Claude Code](https://claude.ai/code) so the horn honks whenever Claude needs your attention — end of response, tool permission prompt, or any choice dialog.

Add this to `~/.claude/settings.json`:

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

## Stack

`psutil` · `sounddevice` · `numpy` · `pystray` · `Pillow`

## Tests

```bash
pytest tests/ -v
```
