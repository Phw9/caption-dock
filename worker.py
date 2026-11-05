"""Capture OCR snapshots and translate every ordered visible utterance."""
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
import hashlib
import logging
from pathlib import Path
from queue import SimpleQueue
from threading import Event
from time import monotonic

from pipeline import Ocr, Translator
from speech import Speech, split_speech, translate_caption
from transcript import CaptionRequest, MAX_TRANSCRIPT_ROWS, TranscriptBuffer
import screen

ASSETS = Path(__file__).resolve().parent / "assets"
POLL_SECONDS = 0.18
MAX_TRANSLATION_CACHE = 200


def translate_timed(speech: Speech, translate: Callable[[str], str]) -> tuple[Speech, int]:
    started = monotonic()
    caption = translate_caption(speech, translate)
    return caption, round((monotonic() - started) * 1000)


class CaptionWorker:
    def __init__(self, region, stop, events, capture_lock, separate_speakers, measure) -> None:
        self.region = region
        self.stop = stop
        self.events = events
        self.capture_lock = capture_lock
        self.separate_speakers = separate_speakers
        self.measure = measure
        self.buffer = TranscriptBuffer()
        self.waiting: OrderedDict[int, CaptionRequest] = OrderedDict()
        self.cache: OrderedDict[Speech, str] = OrderedDict()
        self.previous = None
        self.speaker = ""
        self.future = None
        self.request = None

    def observe(self, ocr: Ocr) -> None:
        captured_at = monotonic()
        with self.capture_lock:
            frame = screen.capture(self.region)
        fingerprint = hashlib.blake2s(frame.tobytes()).digest()
        if fingerprint != self.previous:
            rows = ocr.read_lines(frame, self.separate_speakers)
            speech = split_speech(rows, self.separate_speakers, self.speaker,
                                  merge_same_speaker=False)
            if speech:
                self.speaker = speech[-1].speaker
            self.buffer.observe(speech, monotonic(), captured_at)
            if self.measure:
                self.events.put(("ocr_timing", round((monotonic() - captured_at) * 1000)))
            self.previous = fingerprint

    def enqueue(self) -> None:
        for request in self.buffer.take(monotonic()):
            self.events.put(("pending", request))
            if request.speech in self.cache:
                self.waiting.pop(request.identifier, None)
                self.events.put(("caption", (request, self.cache[request.speech], 0)))
            else:
                self.waiting[request.identifier] = request
        while len(self.waiting) > MAX_TRANSCRIPT_ROWS:
            self.waiting.popitem(last=False)

    def receive(self) -> None:
        if self.future is not None and self.future.done():
            translated, inference_ms = self.future.result()
            self.cache[self.request.speech] = translated.text
            self.cache.move_to_end(self.request.speech)
            while len(self.cache) > MAX_TRANSLATION_CACHE:
                self.cache.popitem(last=False)
            if not self.stop.is_set():
                self.events.put(("caption", (self.request, translated.text, inference_ms)))
            self.future = None

    def schedule(self, executor, translator: Translator) -> None:
        if self.future is None and self.waiting and not self.stop.is_set():
            _identifier, self.request = self.waiting.popitem(last=False)
            self.future = executor.submit(translate_timed, self.request.speech, translator.translate)

    def run(self, ocr: Ocr, executor, translator: Translator) -> None:
        self.events.put(("ready", "영어 자막을 읽는 중…"))
        while not self.stop.is_set():
            started = monotonic()
            self.observe(ocr)
            self.enqueue()
            self.receive()
            self.schedule(executor, translator)
            self.stop.wait(max(0.0, POLL_SECONDS - (monotonic() - started)))


def read_captions(
    region: screen.Region, stop: Event, events: SimpleQueue, capture_lock,
    separate_speakers: bool = False, measure: bool = False,
) -> None:
    translator = None
    try:
        translator = Translator(ASSETS / "opus")
        with Ocr(ASSETS) as ocr, ThreadPoolExecutor(max_workers=1) as executor:
            worker = CaptionWorker(region, stop, events, capture_lock, separate_speakers, measure)
            worker.run(ocr, executor, translator)
    except (OSError, RuntimeError, ValueError):
        logging.exception("Caption worker failed")
        events.put(("error", "화면을 읽거나 번역을 시작하지 못했습니다."))
    finally:
        translator = None
        events.put(("stopped", ""))
