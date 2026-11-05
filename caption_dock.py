"""Caption Dock for Windows."""
import argparse
from collections import deque
import json
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Event, Lock, Thread
from time import monotonic
import tkinter as tk
from tkinter import ttk

from speech import Speech
from viewer import Overlay
from worker import ASSETS, read_captions
import screen


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
        text="영어 자막 전체를 드래그하세요. 취소하려면 Esc를 누르세요.",
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
            finish(screen.Region(min(start[0], x), min(start[1], y),
                                 abs(start[0] - x), abs(start[1] - y)))

    canvas.bind("<ButtonPress-1>", begin)
    canvas.bind("<B1-Motion>", drag)
    canvas.bind("<ButtonRelease-1>", release)
    picker.bind("<Escape>", lambda _event: finish(None))
    screen.place(screen.hwnd(picker), bounds)
    picker.focus_force()


class CaptionDock:
    def __init__(self, root: tk.Tk, performance_report: Path | None = None) -> None:
        self.root = root
        self.region = None
        self.performance_report = performance_report
        self.performance_error = ""
        self.measurements: deque[dict] = deque(maxlen=200)
        self.ocr_ms: deque[int] = deque(maxlen=200)
        self.stop = None
        self.closing = False
        self.translation: str | Speech = ""
        self.capture_lock = Lock()
        self.events = SimpleQueue()
        root.title("Caption Dock")
        root.geometry("+36+36")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.overlay = Overlay(root)
        self.status = tk.StringVar(value="영어 자막 전체를 드래그해 선택하세요.")
        content = ttk.Frame(root, padding=18)
        content.pack(fill="both", expand=True)
        actions = ttk.Frame(content)
        actions.pack(fill="x")
        self.select = ttk.Button(actions, text="영역 선택", command=self.pick)
        self.select.pack(side="left")
        self.toggle = ttk.Button(actions, text="시작", command=self.toggle_capture,
                                 state="disabled")
        self.toggle.pack(side="left", padx=6)
        ttk.Button(actions, text="번역창", command=self.overlay.reopen).pack(side="left")
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
        self.overlay.clear()
        self.overlay.reopen()
        self.select.state(["disabled"])
        self.toggle.configure(text="일시정지")
        self.toggle.state(["!disabled"])
        self.status.set("번역을 준비하는 중…")
        Thread(
            target=read_captions,
            args=(self.region, self.stop, self.events, self.capture_lock,
                  self.performance_report is not None),
            daemon=True,
        ).start()

    def toggle_capture(self) -> None:
        if self.stop is None:
            self.start()
        else:
            self.stop.set()
            self.toggle.state(["disabled"])
            self.status.set("멈추는 중…")

    def stopped(self) -> None:
        if self.closing:
            self.stop = None
            self.root.destroy()
        else:
            if self.stop is not None and self.stop.is_set():
                self.status.set("일시정지됨")
            self.stop = None
            self.select.state(["!disabled"])
            self.toggle.configure(text="시작")
            self.toggle.state(["!disabled"])

    def drain(self) -> None:
        while not self.events.empty():
            try:
                kind, value = self.events.get_nowait()
            except Empty:
                break
            if kind == "stopped":
                self.stopped()
                if self.closing:
                    break
            elif self.stop is not None and not self.stop.is_set():
                self.receive(kind, value)
        if not self.closing or self.stop is not None:
            self.root.after(60, self.drain)

    def receive(self, kind: str, value) -> None:
        if kind == "pending":
            self.overlay.pending(value)
        elif kind == "caption":
            request, translated, inference_ms = value
            if self.overlay.complete(request, translated):
                self.translation = Speech(request.speech.speaker, translated)
                if self.performance_report is not None:
                    self.record_measurement({
                        "observed_at": request.observed_at,
                        "source_words": len(request.speech.text.split()),
                        "inference_ms": inference_ms,
                        "speaker_in_body": bool(request.speech.speaker
                                                and request.speech.speaker in request.speech.text),
                    })
        elif kind == "ocr_timing":
            self.ocr_ms.append(value)
        elif kind in ("ready", "error"):
            self.status.set(value)

    def record_measurement(self, sample: dict) -> None:
        sample["caption_observed_to_overlay_ms"] = round(
            (monotonic() - sample.pop("observed_at")) * 1000
        )
        self.measurements.append(sample)
        try:
            self.performance_report.write_text(json.dumps({
                "ocr_ms": list(self.ocr_ms), "samples": list(self.measurements),
            }, indent=2) + "\n", encoding="utf-8")
        except OSError as error:
            self.performance_error = str(error)
            self.performance_report = None
            self.status.set("성능 기록을 저장하지 못했습니다.")

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
    parser.add_argument("--performance-report", type=Path, metavar="REPORT")
    args = parser.parse_args()
    screen.set_dpi(screen.DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    if args.self_test:
        from verification import verify
        verify(args.self_test, ASSETS, Overlay)
    else:
        root = tk.Tk()
        CaptionDock(root, args.performance_report)
        root.mainloop()


if __name__ == "__main__":
    main()
