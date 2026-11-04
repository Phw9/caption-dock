"""Smoke test the packaged Windows path against a synthetic caption."""
import json
from pathlib import Path
import tkinter as tk
from time import perf_counter

from captions import SentenceBuffer
from pipeline import Ocr, Translator
import screen

SAMPLE = "The meeting starts in five minutes."


def check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def verify(report: Path, assets: Path, overlay_factory) -> None:
    # The report includes only synthetic text. The app never logs real captions.
    result = {"passed": False}
    root = None
    try:
        sentences = SentenceBuffer()
        sentences.observe("The meeting starts in", 1.0)
        check(sentences.take(1.5) is None, "Partial caption was emitted early.")
        sentences.observe("starts in five minutes.", 1.6)
        check(sentences.take(2.0) == SAMPLE, "Rolling captions did not form a sentence.")
        check(sentences.take(2.2) is None, "Duplicate caption was emitted.")
        sentences.observe("", 2.3)
        check(sentences.take(4.9) == "", "Disappearing captions did not clear.")
        result["rolling_sentence"] = True

        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        tk.Label(
            root, text=SAMPLE, font=("Segoe UI", 24),
            background="#121820", foreground="white",
        ).pack(fill="both", expand=True)
        region = screen.Region(100, 150, 720, 90)
        screen.place(screen.hwnd(root), region)
        root.update()
        screen.flush_compositor()
        reference = screen.capture(region)

        overlay = tk.Toplevel(root)
        overlay.withdraw()
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True, "-alpha", 0.98)
        tk.Label(overlay, text="이 창은 캡처에서 제외됩니다.",
                 background="#bd1616", foreground="white",
                 font=("Malgun Gothic", 22)).pack(fill="both", expand=True)
        handle = screen.hwnd(overlay)
        overlay.deiconify()
        root.update()
        screen.place(handle, region)
        root.update()
        screen.flush_compositor()
        covered = screen.capture(region)
        check(reference.tobytes() != covered.tobytes(),
              "Test overlay did not cover the caption before exclusion.")
        check(screen.exclude_overlay(handle),
              "Windows did not accept capture exclusion.")
        root.update()
        screen.flush_compositor()
        frame = screen.capture(region)
        check(reference.tobytes() == frame.tobytes(),
              "The captured region changed despite overlay exclusion.")
        result["overlay_excluded"] = True

        with Ocr(assets) as ocr:
            started = perf_counter()
            text = ocr.read(frame)
            result["ocr_ms"] = round((perf_counter() - started) * 1000)
        result["recognized"] = text
        check(text == SAMPLE, "OCR did not read the synthetic caption exactly.")
        started = perf_counter()
        engine = Translator(assets / "opus")
        result["model_load_ms"] = round((perf_counter() - started) * 1000)
        durations = []
        for _ in range(5):
            started = perf_counter()
            translated = engine.translate(text)
            durations.append(round((perf_counter() - started) * 1000))
        result["translation_ms"] = durations
        result["translated"] = translated
        check("회의" in translated and "시작" in translated,
              "Expected Korean meeting and start in the translation.")
        overlay.destroy()
        actual_overlay = overlay_factory(root)
        check(actual_overlay.excluded, "Caption Dock overlay could not be excluded.")
        check(actual_overlay.try_cover(translated, region),
              "The runtime cover check did not accept the unchanged capture.")
        root.update()
        screen.flush_compositor()
        check(actual_overlay.window.winfo_viewable(), "Caption Dock overlay was hidden.")
        check(screen.capture(region).tobytes() == reference.tobytes(),
              "Caption Dock overlay interfered with subsequent capture.")
        check(screen.set_affinity(actual_overlay.handle, 0),
              "Could not simulate an overlay that appears in capture.")
        check(not actual_overlay.try_cover(translated, region),
              "The runtime cover check accepted an obstructed capture.")
        actual_overlay.show(translated, region, cover=False)
        root.update()
        screen.flush_compositor()
        check(screen.capture(region).tobytes() == reference.tobytes(),
              "The adjacent overlay interfered with capture.")
        result["cover_fallback"] = True
        result["passed"] = True
    except (OSError, RuntimeError, ValueError, tk.TclError) as error:
        result["error"] = str(error)
        raise SystemExit(1) from error
    finally:
        if root is not None:
            root.destroy()
        report.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
