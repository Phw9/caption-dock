"""A movable, resizable translation window with bounded live history."""
import hashlib
import tkinter as tk

from speech import Speech, speaker_label
from transcript import CaptionRequest, TranscriptHistory
import screen

BACKGROUND = "#121820"
FOREGROUND = "#f2f6fb"
TOOLBAR = "#1c2835"
MUTED = "#a4b4c4"
SPEAKER_COLORS = (("#233b52", "#c3e2ff"), ("#303c35", "#d2ead7"),
                  ("#40344b", "#ead6fa"))
DEFAULT_FONT_SIZE = 16
MIN_FONT_SIZE = 10
MAX_FONT_SIZE = 32


class Overlay:
    def __init__(self, root: tk.Tk) -> None:
        self.history = TranscriptHistory()
        self.font_size = DEFAULT_FONT_SIZE
        self.dismissed = False
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title("Caption Dock 번역")
        self.window.configure(background=BACKGROUND)
        self.window.geometry("660x500+80+220")
        self.window.minsize(360, 200)
        self.window.resizable(True, True)
        self.window.attributes("-topmost", True)
        self.window.protocol("WM_DELETE_WINDOW", self.dismiss)
        self.pinned = tk.BooleanVar(value=True)
        self.make_toolbar()
        content = tk.Frame(self.window, background=BACKGROUND)
        content.pack(fill="both", expand=True)
        self.text = tk.Text(
            content, background=BACKGROUND, foreground=FOREGROUND,
            insertbackground=FOREGROUND, font=("Malgun Gothic", self.font_size),
            wrap="word", relief="flat", borderwidth=0, padx=16, pady=14,
            state="disabled", spacing1=0, spacing3=0,
        )
        scrollbar = tk.Scrollbar(content, command=self.text.yview)
        scrollbar.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(fill="both", expand=True)
        self.text.bind("<Control-MouseWheel>", self.zoom_wheel)
        self.window.bind("<Control-plus>", lambda _event: self.zoom(1))
        self.window.bind("<Control-minus>", lambda _event: self.zoom(-1))
        self.handle = screen.hwnd(self.window)
        self.excluded = screen.exclude_overlay(self.handle, interactive=True)
        self.window.bind("<Map>", self.refresh_capture)
        self.render()

    def refresh_capture(self, event) -> None:
        if event.widget is self.window:
            self.handle = screen.get_ancestor(self.window.winfo_id(), screen.GA_ROOT)
            self.excluded = screen.exclude_overlay(self.handle, interactive=True)

    def make_toolbar(self) -> None:
        toolbar = tk.Frame(self.window, background=TOOLBAR, padx=10, pady=7)
        toolbar.pack(fill="x")
        tk.Label(toolbar, text="글씨", background=TOOLBAR, foreground=FOREGROUND,
                 font=("Malgun Gothic", 10)).pack(side="left", padx=(0, 8))
        for label, delta in (("−", -1), ("+", 1)):
            tk.Button(
                toolbar, text=label, width=3, relief="flat", background=TOOLBAR,
                foreground=FOREGROUND, activebackground="#304156",
                activeforeground=FOREGROUND, font=("Malgun Gothic", 11),
                command=lambda amount=delta: self.zoom(amount),
            ).pack(side="left", padx=2)
        tk.Button(toolbar, text="지우기", relief="flat", background=TOOLBAR,
                  foreground=FOREGROUND, activebackground="#304156",
                  activeforeground=FOREGROUND, command=self.clear).pack(side="right")
        tk.Checkbutton(
            toolbar, text="항상 위", variable=self.pinned, command=self.pin,
            background=TOOLBAR, foreground=FOREGROUND, selectcolor=BACKGROUND,
            activebackground=TOOLBAR, activeforeground=FOREGROUND,
        ).pack(side="right", padx=10)

    def pin(self) -> None:
        self.window.attributes("-topmost", self.pinned.get())

    def reopen(self) -> None:
        self.dismissed = False
        self.window.deiconify()
        self.window.lift()

    def dismiss(self) -> None:
        self.dismissed = True
        self.window.withdraw()

    def hide(self) -> None:
        self.window.withdraw()

    def pending(self, request: CaptionRequest) -> None:
        self.history.pending(request)
        self.render()

    def complete(self, request: CaptionRequest, translated: str) -> bool:
        accepted = self.history.translated(request, translated)
        if accepted:
            self.render()
            if not self.dismissed and self.window.state() == "withdrawn":
                self.window.deiconify()
        return accepted

    def show(self, text: str | Speech, region: screen.Region, cover: bool) -> None:
        speech = text if isinstance(text, Speech) else Speech("", text)
        request = CaptionRequest(-1, speech, 0.0)
        self.pending(request)
        self.complete(request, speech.text)

    def clear(self) -> None:
        self.history.clear()
        self.render()

    def zoom(self, amount: int) -> None:
        self.font_size = min(MAX_FONT_SIZE, max(MIN_FONT_SIZE, self.font_size + amount))
        self.render()

    def zoom_wheel(self, event) -> str:
        self.zoom(1 if event.delta > 0 else -1)
        return "break"

    def render(self) -> None:
        at_bottom = self.text.yview()[1] >= 0.985
        top = self.text.index("@0,0")
        self.text.configure(state="normal", font=("Malgun Gothic", self.font_size))
        self.text.delete("1.0", "end")
        self.text.tag_configure("waiting", foreground=MUTED)
        self.text.tag_configure("body", spacing3=14)
        self.text.tag_configure("header", font=("Malgun Gothic", max(10, self.font_size - 5)))
        for index, (background, foreground) in enumerate(SPEAKER_COLORS):
            self.text.tag_configure(
                f"speaker{index}", background=background, foreground=foreground,
                font=("Malgun Gothic", max(10, self.font_size - 5)),
            )
        for entry in self.history.rows.values():
            name = speaker_label(entry.request.speech.speaker)
            if name:
                identity = hashlib.blake2s(entry.request.speech.speaker.encode()).digest()[0]
                self.text.insert("end", " " + name + " ", f"speaker{identity % len(SPEAKER_COLORS)}")
                self.text.insert("end", "\n", "header")
            self.text.insert("end", entry.translated or "번역 중…",
                             ("body",) if entry.translated else ("body", "waiting"))
            self.text.insert("end", "\n", "body")
        if not self.history.rows:
            self.text.insert("end", "번역을 기다리는 중…", "waiting")
        self.text.configure(state="disabled")
        if at_bottom:
            self.text.see("end")
        else:
            self.text.yview(top)
        self.window.update_idletasks()
