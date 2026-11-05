"""Caption Dock for Windows."""
import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Event, Lock, Thread
from time import monotonic
import tkinter as tk
from tkinter import ttk

from pipeline import Ocr, Translator
from speech import Speech, SpeechBuffer, speaker_label, split_speech, translate_caption
import screen

ASSETS = Path(__file__).resolve().parent / "assets"
POLL_SECONDS = 0.18
MAX_WAITING_TRANSLATIONS = 4
BACKGROUND = "#121820"
FOREGROUND = "#f2f6fb"
SPEAKER_COLORS = (("#233b52", "#c3e2ff"), ("#303c35", "#d2ead7"),
                  ("#40344b", "#ead6fa"))


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
        text="영어 자막을 드래그하세요. 취소하려면 Esc를 누르세요.",
        fill="white", font=("Malgun Gothic", 20, "bold"),
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
        self.window.configure(background=BACKGROUND)
        self.speaker = tk.Label(
            self.window, font=("Malgun Gothic", 10), anchor="w", padx=9, pady=3,
        )
        self.label = tk.Label(
            self.window, background=BACKGROUND, foreground=FOREGROUND,
            font=("Malgun Gothic", 16), justify="left", anchor="w", padx=14, pady=10,
        )
        self.label.pack(fill="both", expand=True)
        self.handle = screen.hwnd(self.window)
        self.excluded = screen.exclude_overlay(self.handle)

    def hide(self) -> None:
        self.window.withdraw()

    def show(self, text: str | Speech, region: screen.Region, cover: bool) -> None:
        name = speaker_label(text.speaker) if isinstance(text, Speech) else ""
        body = text.text if isinstance(text, Speech) else text
        if name:
            identity = hashlib.blake2s(text.speaker.encode()).digest()[0]
            color_index = identity % len(SPEAKER_COLORS)
            background, foreground = SPEAKER_COLORS[color_index]
            self.speaker.configure(text="화자  " + name, background=background,
                                   foreground=foreground)
            self.speaker.pack(before=self.label, anchor="w", padx=14, pady=(10, 0))
        else:
            self.speaker.pack_forget()
        self.label.configure(
            text=body, wraplength=max(50, region.width - 28),
            justify="left" if name else "center", anchor="w" if name else "center",
        )
        self.label.update_idletasks()
        height = self.window.winfo_reqheight()
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

    def try_cover(self, text: str | Speech, region: screen.Region) -> bool:
        self.hide()
        self.window.update_idletasks()
        screen.flush_compositor()
        before = screen.capture(region)
        self.show(text, region, cover=True)
        self.window.update_idletasks()
        screen.flush_compositor()
        after = screen.capture(region)
        # A blank/redacted capture cannot demonstrate that the original is visible.
        return bool(
            self.window.winfo_viewable()
            and (before != before[0, 0]).any()
            and before.tobytes() == after.tobytes()
        )


def read_captions(
    region: screen.Region, stop: Event, events: SimpleQueue, capture_lock,
    separate_speakers: bool = False,
) -> None:
    translator = None
    try:
        translator = Translator(ASSETS / "opus")
        with Ocr(ASSETS) as ocr, ThreadPoolExecutor(max_workers=1) as executor:
            sentences = SpeechBuffer()
            waiting: deque[Speech] = deque(maxlen=MAX_WAITING_TRANSLATIONS)
            future = None
            previous = None
            events.put(("ready", "영어 자막을 읽는 중…"))
            while not stop.is_set():
                started = monotonic()
                with capture_lock:
                    frame = screen.capture(region)
                fingerprint = hashlib.blake2s(frame.tobytes()).digest()
                if fingerprint != previous:
                    sentences.observe(
                        split_speech(
                            ocr.read_lines(frame, separate_speakers),
                            separate_speakers, sentences.active,
                        ),
                        monotonic(),
                    )
                    previous = fingerprint
                waiting.extend(sentences.take(monotonic()))
                if future is not None and future.done():
                    translation = future.result()
                    if not stop.is_set():
                        events.put(("caption", translation))
                    future = None
                if future is None and waiting and not stop.is_set():
                    next_caption = waiting.popleft()
                    if next_caption.text:
                        future = executor.submit(
                            translate_caption, next_caption, translator.translate
                        )
                    else:
                        events.put(("caption", ""))
                stop.wait(max(0.0, POLL_SECONDS - (monotonic() - started)))
    except (OSError, RuntimeError, ValueError):
        events.put(("error", "화면을 읽거나 번역을 시작하지 못했습니다."))
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
        self.translation: str | Speech = ""
        self.cover_checked = False
        self.capture_lock = Lock()
        self.events = SimpleQueue()
        root.title("Caption Dock")
        root.geometry("+36+36")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.overlay = Overlay(root)
        self.cover = tk.BooleanVar(value=False)
        self.speakers = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="영어 자막 영역을 선택하세요.")
        content = ttk.Frame(root, padding=18)
        content.pack(fill="both", expand=True)
        actions = ttk.Frame(content)
        actions.pack(fill="x")
        self.select = ttk.Button(actions, text="영역 선택", command=self.pick)
        self.select.pack(side="left")
        self.toggle = ttk.Button(actions, text="시작", command=self.toggle_capture,
                                 state="disabled")
        self.toggle.pack(side="left", padx=6)
        self.mode = ttk.Checkbutton(content, text="영어 자막 가리기",
                                    variable=self.cover, command=self.change_mode)
        self.mode.pack(anchor="w", pady=(12, 0))
        self.speaker_mode = ttk.Checkbutton(
            content, text="Teams 화자 이름 분리", variable=self.speakers
        )
        self.speaker_mode.pack(anchor="w", pady=(6, 0))
        if not self.overlay.excluded:
            self.mode.state(["disabled"])
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
                self.status.set("영어 자막 줄 전체를 다시 선택하세요.")

    def start(self) -> None:
        self.stop = Event()
        self.translation = ""
        self.cover_checked = False
        self.select.state(["disabled"])
        self.speaker_mode.state(["disabled"])
        self.toggle.configure(text="일시정지")
        self.toggle.state(["!disabled"])
        self.status.set("번역을 준비하는 중…")
        Thread(
            target=read_captions,
            args=(self.region, self.stop, self.events, self.capture_lock,
                  self.speakers.get()),
            daemon=True,
        ).start()

    def toggle_capture(self) -> None:
        if self.stop is None:
            self.start()
        else:
            self.stop.set()
            self.overlay.hide()
            self.toggle.state(["disabled"])
            self.status.set("멈추는 중…")

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
                    self.status.set("일시정지됨")
                self.stop = None
                self.select.state(["!disabled"])
                self.speaker_mode.state(["!disabled"])
                self.toggle.configure(text="시작")
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

    def change_mode(self) -> None:
        self.cover_checked = False
        self.redraw()

    def redraw(self) -> None:
        if self.stop is not None and not self.stop.is_set() and self.translation:
            with self.capture_lock:
                if self.cover.get() and not self.cover_checked:
                    try:
                        self.cover_checked = self.overlay.try_cover(
                            self.translation, self.region
                        )
                    except OSError:
                        self.cover_checked = False
                    if not self.cover_checked:
                        self.cover.set(False)
                        self.status.set(
                            "원문을 읽을 수 있도록 번역을 옆에 표시합니다."
                        )
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
            self.status.set("종료하는 중…")


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
