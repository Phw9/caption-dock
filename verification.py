"""Smoke test the packaged Windows path against a synthetic caption."""
import json
from pathlib import Path
import tkinter as tk
from time import perf_counter

from captions import SentenceBuffer
from pipeline import Ocr, Translator
from speech import Speech, SpeechBuffer, display_translation, split_speech
import screen

SAMPLE = "The meeting starts in five minutes."


def verify_avatar_caption(root: tk.Tk, assets: Path) -> dict:
    for child in root.winfo_children():
        child.destroy()
    root.configure(background="white")
    region = screen.Region(100, 150, 760, 180)
    screen.place(screen.hwnd(root), region)
    for top in (8, 76):
        avatar = tk.Canvas(root, width=40, height=40, background="white",
                           highlightthickness=0)
        avatar.create_oval(0, 0, 39, 39, fill="#d9eff2", outline="")
        avatar.create_text(20, 20, text="박현", font=("Malgun Gothic", 12),
                           fill="#47777b")
        avatar.place(x=16, y=top)
        tk.Label(root, text="alex@example.com", font=("Segoe UI", 10, "bold"),
                 background="white", foreground="#242424").place(x=68, y=top)
    tk.Label(root, text="We need to update the", font=("Segoe UI", 16),
             background="white", foreground="#242424").place(x=68, y=28)
    tk.Label(root, text="camera calibration before the next release.",
             font=("Segoe UI", 16), background="white",
             foreground="#242424").place(x=68, y=96)
    root.update()
    screen.flush_compositor()
    with Ocr(assets) as ocr:
        speech = split_speech(ocr.read_lines(screen.capture(region), True), True)
    expected = "We need to update the camera calibration before the next release."
    check(speech == [Speech("alex@example.com", expected)],
          "Avatar or repeated account text entered the Teams speech body.")
    return {"speaker": speech[0].speaker, "source": speech[0].text}


def verify_speaker_caption(root: tk.Tk, assets: Path, engine: Translator) -> dict:
    for child in root.winfo_children():
        child.destroy()
    root.geometry("760x170+100+150")
    name = tk.Label(
        root, text="Alex Kim", font=("Segoe UI", 12, "bold"),
        foreground="#b0b0b0", background="#202020", anchor="w",
    )
    name.pack(fill="x", padx=12, pady=(8, 10))
    body = tk.Label(
        root, text="We need to update the\ncamera", font=("Segoe UI", 20),
        foreground="white", background="#202020", justify="left", anchor="w",
    )
    body.pack(fill="both", expand=True, padx=12)
    root.configure(background="#202020")
    region = screen.Region(100, 150, 760, 170)
    root.update()
    screen.flush_compositor()
    buffer = SpeechBuffer()
    with Ocr(assets) as ocr:
        first = split_speech(ocr.read_lines(screen.capture(region)), True)
        check(bool(first) and first[0].speaker == "Alex Kim",
              "The OCR name row was not preserved separately.")
        buffer.observe(first, 1.0)
        check(not buffer.take(1.5), "A partial Teams caption was translated early.")
        body.configure(text="camera calibration before\nthe next release.")
        root.update()
        screen.flush_compositor()
        second = split_speech(ocr.read_lines(screen.capture(region)), True)
        buffer.observe(second, 1.6)
        utterances = buffer.take(2.0)
    expected = "We need to update the camera calibration before the next release."
    check(len(utterances) == 1 and utterances[0].text == expected,
          "Teams caption rows were not assembled without the name.")
    translated = engine.translate(utterances[0].text)
    rendered = display_translation(utterances[0], translated)
    check(rendered.startswith("Alex Kim\n"), "The display name lost its own row.")
    check(any("\uac00" <= char <= "\ud7a3" for char in translated),
          "The completed Teams caption was not translated to Korean.")
    return {"speaker": utterances[0].speaker, "source": expected, "translated": translated}


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
        actual_overlay.show(Speech("alex@example.com", translated), region, cover=False)
        root.update()
        check(actual_overlay.speaker.cget("text") == "화자  alex",
              "The speaker chip did not shorten the account address.")
        check(actual_overlay.label.cget("text") == translated,
              "The speaker account entered the translated body label.")
        check(actual_overlay.speaker.winfo_y() < actual_overlay.label.winfo_y(),
              "The speaker chip was not placed above the translation.")
        actual_overlay.show(translated, region, cover=False)
        root.update()
        check(not actual_overlay.speaker.winfo_ismapped(),
              "A previous speaker chip remained on an anonymous caption.")
        result["speaker_chip"] = True
        result["teams_name_rows"] = verify_speaker_caption(root, assets, engine)
        result["teams_avatar_rows"] = verify_avatar_caption(root, assets)
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
