import threading
import tkinter as tk
from tkinter import ttk

import pystray
from PIL import Image, ImageDraw

from shared_state import SharedState


def _make_icon_image() -> Image.Image:
    img = Image.new("RGB", (64, 64), color=(30, 30, 30))
    draw = ImageDraw.Draw(img)
    draw.ellipse([8, 8, 56, 56], fill=(0, 180, 100))
    return img


def _open_settings(state: SharedState) -> None:
    def run():
        root = tk.Tk()
        root.title("TachTone Settings")
        root.resizable(False, False)

        tk.Label(root, text="Volume", padx=16, pady=8).pack()

        slider = ttk.Scale(
            root,
            from_=0,
            to=100,
            orient="horizontal",
            length=200,
            command=lambda val: state.set_volume(int(float(val))),
        )
        slider.set(state.get_volume())
        slider.pack(padx=16, pady=(0, 16))

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
