import math
import threading
import tkinter as tk
from tkinter import ttk

import pystray
from PIL import Image, ImageDraw

from shared_state import SharedState


def _make_icon_image() -> Image.Image:
    S = 128  # draw at 2× then downscale for clean edges
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = 64, 64

    # --- Dark circular background ---
    draw.ellipse([2, 2, S-2, S-2], fill=(14, 16, 36), outline=(50, 60, 110), width=3)

    # --- Gauge arc: 270° sweep, orange/amber ---
    r = 52
    box = [cx-r, cy-r, cx+r, cy+r]
    draw.arc(box, start=135, end=405, fill=(255, 125, 0), width=10)

    # --- Tick marks along the arc ---
    for i in range(10):
        a = math.radians(135 + i * 30)
        r_out = 50
        r_in  = 40 if i % 3 == 0 else 44   # major vs minor ticks
        x1, y1 = cx + r_out * math.cos(a), cy + r_out * math.sin(a)
        x2, y2 = cx + r_in  * math.cos(a), cy + r_in  * math.sin(a)
        draw.line([x1, y1, x2, y2], fill=(255, 200, 110), width=2 if i % 3 == 0 else 1)

    # --- Needle at ~35% sweep ---
    a_needle = math.radians(135 + 0.35 * 270)
    nx, ny = cx + 40 * math.cos(a_needle), cy + 40 * math.sin(a_needle)
    bx, by = cx + 10 * math.cos(a_needle + math.pi), cy + 10 * math.sin(a_needle + math.pi)
    draw.line([bx, by, nx, ny], fill=(255, 255, 255), width=4)
    draw.ellipse([cx-5, cy-5, cx+5, cy+5], fill=(190, 190, 210))
    draw.ellipse([cx-3, cy-3, cx+3, cy+3], fill=(60, 60, 80))

    # --- Musical note (upper-right, blue) ---
    nox, noy = 90, 22
    draw.ellipse([nox-8, noy-5, nox+5, noy+6], fill=(55, 145, 255))   # note head
    draw.line([nox+4, noy, nox+4, noy-22], fill=(55, 145, 255), width=4)  # stem
    draw.line([nox+4, noy-22, nox+20, noy-14], fill=(55, 145, 255), width=3)  # flag 1
    draw.line([nox+4, noy-16, nox+20, noy-9],  fill=(55, 145, 255), width=2)  # flag 2

    # --- Speaker + waves (lower-left, orange) ---
    spx, spy = 22, 90
    # Cabinet body
    draw.polygon([
        (spx-6, spy-5), (spx-6, spy+5),
        (spx+4, spy+9), (spx+4, spy-9),
    ], fill=(255, 140, 20))
    # Mounting block
    draw.rectangle([spx-12, spy-4, spx-6, spy+4], fill=(255, 140, 20))
    # Sound waves
    mouth = spx + 4
    for i, rr in enumerate([10, 16, 22]):
        draw.arc([mouth-rr, spy-rr, mouth+rr, spy+rr],
                 start=300, end=60, fill=(255, 175, 70), width=2)

    return img.resize((64, 64), Image.LANCZOS).convert("RGB")


def _open_settings(state: SharedState) -> None:
    def run():
        root = tk.Tk()
        root.title("TachTone Settings")
        root.resizable(False, False)

        channels = [
            ("Master Volume",       state.get_volume,       state.set_volume),
            None,  # separator
            ("CPU Tone",            state.get_cpu_vol,      state.set_cpu_vol),
            ("Interrupts (vibrato)",state.get_interrupts_vol, state.set_interrupts_vol),
            ("Network Bell/Piano",  state.get_network_vol,  state.set_network_vol),
            ("Disk Tom",            state.get_disk_vol,     state.set_disk_vol),
            ("Honk Honk",           state.get_honk_vol,     state.set_honk_vol),
        ]

        outer = tk.Frame(root, padx=20, pady=14)
        outer.pack()

        grid_row = 0
        for entry in channels:
            if entry is None:
                ttk.Separator(outer, orient="horizontal").grid(
                    row=grid_row, column=0, columnspan=3, sticky="ew", pady=6
                )
                grid_row += 1
                continue

            label, getter, setter = entry
            val_var = tk.StringVar(value=str(getter()))

            tk.Label(outer, text=label, width=22, anchor="w").grid(
                row=grid_row, column=0, sticky="w"
            )

            def make_cmd(s, v):
                def cmd(raw):
                    n = int(float(raw))
                    s(n)
                    v.set(str(n))
                return cmd

            scale = ttk.Scale(
                outer, from_=0, to=100, orient="horizontal", length=180,
                command=make_cmd(setter, val_var),
            )
            scale.set(getter())
            scale.grid(row=grid_row, column=1, padx=10)

            tk.Label(outer, textvariable=val_var, width=4, anchor="e").grid(
                row=grid_row, column=2
            )

            grid_row += 1

        root.mainloop()

    threading.Thread(target=run, daemon=True).start()


class TrayApp:
    def __init__(self, state: SharedState, on_quit):
        self._state = state
        self._on_quit = on_quit

        menu = pystray.Menu(
            pystray.MenuItem("Settings", self._on_settings),
            pystray.MenuItem("Quit", self._on_quit_clicked),
        )
        self._icon = pystray.Icon(
            "TachTone",
            _make_icon_image(),
            "TachTone",
            menu,
        )

    def _on_settings(self, icon, item):
        _open_settings(self._state)

    def _on_quit_clicked(self, icon, item):
        icon.stop()
        self._on_quit()

    def run(self) -> None:
        self._icon.run()
