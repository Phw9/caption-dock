"""Caption Dock for Windows."""
import argparse
import hashlib
from pathlib import Path
from queue import Empty, SimpleQueue
import sys
from threading import Event, Thread
from time import monotonic
import tkinter as tk
from tkinter import ttk

from pipeline import CaptionGate, Ocr, Translator
import screen

ASSETS = Path(__file__).resolve().parent / "assets"
POLL_SECONDS = 0.18
BACKGROUND = "#121820"
FOREGROUND = "#f2f6fb"


def select_region(root: tk.Tk, done) -> None:
    bounds = screen.desktop()
    root.withdraw()
    picker = tk.Toplevel(root)
    picker.overrideredirect(True)
    picker.attributes("-alpha", 0.40, "-topmost", True)
    canvas = tk.Canvas(picker, background="#112339", highlightthickness=0,
                       cursor="crosshair")
    canvas.pack(fill="both", expand=True)
    canvas.create_text(
        bounds.width // 2, 60,
        text="Drag around the English captions   •   Esc to cancel",
        fill="white", font=("Segoe UI", 24, "bold"),
    )
    start = None
    outline = canvas.create_rectangle(0, 0, 0, 0, outline="white", width=3)

    def begin(_event) -> None:
        nonlocal start
        start = screen.cursor()

    def drag(_event) -> None:
        if start is not None:
            x, y = screen.cursor()
            canvas.coords(outline, start[0] - bounds.x, start[1] - bounds.y,
                          x - bounds.x, y - bounds.y)

    def finish(region: screen.Region | None) -> None:
        picker.destroy()
        root.deiconify()
        done(region)

    def release(_event) -> None:
        if start is not None:
            x, y = screen.cursor()
            region = screen.Region(
                min(start[0], x), min(start[1], y),
                abs(start[0] - x), abs(start[1] - y),
            )
            finish(region)

    canvas.bind("<ButtonPress-1>", begin)
    canvas.bind("<B1-Motion>", drag)
    canvas.bind("<ButtonRelease-1>", release)
    picker.bind("<Escape>", lambda _event: finish(None))
    screen.place(screen.hwnd(picker), bounds)
    picker.focus_force()


class Overlay:
    def __init__(self, root: tk.Tk) -> None:
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True, "-alpha", 0.98)
        self.label = tk.Label(
            self.window, background=BACKGROUND, foreground=FOREGROUND,
            font=("Malgun Gothic", 16), justify="center", padx=12, pady=5,
        )
        self.label.pack(fill="both", expand=True)
        self.handle = screen.hwnd(self.window)
        self.excluded = screen.exclude_overlay(self.handle)

    def hide(self) -> None:
        self.window.withdraw()

    def show(self, text: str, region: screen.Region, cover: bool) -> None:
        self.label.configure(text=text, wraplength=max(50, region.width - 24))
        self.label.update_idletasks()
        height = self.label.winfo_reqheight()
        if cover and self.excluded:
            height = max(height, region.height)
            y = region.y + region.height - height
        else:
            bounds = screen.desktop()
            y = region.y - height - 6
            if y < bounds.y:
                y = region.y + region.height + 6
        self.window.deiconify()
        screen.place(self.handle, screen.Region(region.x, y, region.width, height))


def read_captions(region: screen.Region, stop: Event, events: SimpleQueue) -> None:
    translator = None
    try:
        translator = Translator(ASSETS / "opus")
        with Ocr(ASSETS) as ocr:
            gate = CaptionGate()
            previous = None
            events.put(("ready", "Reading English captions"))
            while not stop.is_set():
                started = monotonic()
                frame = screen.capture(region)
                fingerprint = hashlib.blake2s(frame.tobytes()).digest()
                if fingerprint != previous:
                    gate.observe(ocr.read(frame), monotonic())
                    previous = fingerprint
                caption = gate.take(monotonic())
                if caption is not None:
                    translation = translator.translate(caption) if caption else ""
                    if not stop.is_set():
                        events.put(("caption", translation))
                stop.wait(max(0.0, POLL_SECONDS - (monotonic() - started)))
    except (OSError, RuntimeError, ValueError):
        events.put(("error", "Could not read the screen or load the local model."))
    finally:
        # Release the native worker before the UI permits a restart or exit.
        translator = None
        events.put(("stopped", ""))


class CaptionDock:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.region = None
        self.stop = None
        self.closing = False
        self.translation = ""
        self.events = SimpleQueue()
        root.title("Caption Dock")
        root.geometry("+36+36")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.overlay = Overlay(root)
        self.cover = tk.BooleanVar(value=self.overlay.excluded)
        self.status = tk.StringVar(value="Choose the English caption area.")
        content = ttk.Frame(root, padding=18)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="Caption Dock",
                  font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(content, text="English → Korean  ·  Offline",
                  font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 14))
        actions = ttk.Frame(content)
        actions.pack(fill="x")
        self.select = ttk.Button(actions, text="Select area", command=self.pick)
        self.select.pack(side="left")
        self.toggle = ttk.Button(actions, text="Start", command=self.toggle_capture,
                                 state="disabled")
        self.toggle.pack(side="left", padx=6)
        self.mode = ttk.Checkbutton(content, text="Cover the English captions",
                                    variable=self.cover, command=self.redraw)
        self.mode.pack(anchor="w", pady=(12, 0))
        if not self.overlay.excluded:
            self.mode.state(["disabled"])
            self.status.set("Capture exclusion unavailable. Using adjacent subtitles.")
        ttk.Label(content, textvariable=self.status, wraplength=340,
                  width=48).pack(anchor="w", pady=(8, 0))
        root.after(60, self.drain)

    def pick(self) -> None:
        select_region(self.root, self.selected)

    def selected(self, region: screen.Region | None) -> None:
        if region is not None:
            if 80 <= region.width <= 3200 and 20 <= region.height <= 1000:
                self.region = region
                self.start()
            else:
                self.status.set("Select just the caption lines (80–3200 × 20–1000 px).")

    def start(self) -> None:
        self.stop = Event()
        self.translation = ""
        self.select.state(["disabled"])
        self.toggle.configure(text="Pause")
        self.toggle.state(["!disabled"])
        self.status.set("Loading the offline translation model…")
        Thread(target=read_captions, args=(self.region, self.stop, self.events),
               daemon=True).start()

    def toggle_capture(self) -> None:
        if self.stop is None:
            self.start()
        else:
            self.stop.set()
            self.overlay.hide()
            self.toggle.state(["disabled"])
            self.status.set("Pausing…")

    def drain(self) -> None:
        while not self.events.empty():
            try:
                kind, text = self.events.get_nowait()
            except Empty:
                break
            if kind == "stopped":
                if self.closing:
                    self.stop = None
                    self.root.destroy()
                    break
                if self.stop.is_set():
                    self.status.set("Paused")
                self.stop = None
                self.select.state(["!disabled"])
                self.toggle.configure(text="Start")
                self.toggle.state(["!disabled"])
            elif not self.stop.is_set():
                if kind == "caption":
                    self.translation = text
                    self.redraw()
                elif kind == "ready":
                    self.status.set(text)
                else:
                    self.overlay.hide()
                    if kind == "error":
                        self.status.set(text)
        if not self.closing or self.stop is not None:
            self.root.after(60, self.drain)

    def redraw(self) -> None:
        if self.stop is not None and not self.stop.is_set() and self.translation:
            self.overlay.show(self.translation, self.region, self.cover.get())
        else:
            self.overlay.hide()

    def close(self) -> None:
        if self.stop is None:
            self.root.destroy()
        else:
            self.closing = True
            self.stop.set()
            self.toggle.state(["disabled"])
            self.overlay.hide()
            self.status.set("Closing…")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", type=Path, metavar="REPORT")
    args = parser.parse_args()
    screen.set_dpi(screen.DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    if args.self_test:
        from verification import verify
        verify(args.self_test, ASSETS, Overlay)
    else:
        root = tk.Tk()
        CaptionDock(root)
        root.mainloop()


if __name__ == "__main__":
    main()
