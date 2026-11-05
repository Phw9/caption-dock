"""Preserve OCR rows and separate a Teams speaker heading from speech."""
from collections import OrderedDict
from dataclasses import dataclass
import csv
import io
import re
from collections.abc import Callable

from captions import SentenceBuffer
from captions import sentence_end

MIN_LINE_CONFIDENCE = 35
HEADER_HEIGHT_RATIO = 0.8
MAX_HEADER_WORDS = 8
MAX_SPEAKERS = 8
ACCOUNT_LABEL = re.compile(r"[\w.+-]+\s*@\s*[\w.-]+\.[A-Za-z]{2,}")
TSV_COLUMNS = ("level", "page_num", "block_num", "par_num", "line_num",
               "word_num", "left", "top", "width", "height", "conf", "text")


@dataclass(frozen=True)
class CaptionLine:
    text: str
    top: int
    height: int
    left: int = 0
    confidence: float = 100.0


@dataclass(frozen=True)
class Speech:
    speaker: str
    text: str


def read_tsv(text: str) -> list[CaptionLine]:
    rows: dict[tuple[str, ...], list[dict[str, str]]] = {}
    for row in csv.DictReader(
        io.StringIO(text), fieldnames=TSV_COLUMNS,
        delimiter="\t", quoting=csv.QUOTE_NONE,
    ):
        if row["level"] == "5" and row["text"].strip():
            key = tuple(row[name] for name in ("block_num", "par_num", "line_num"))
            rows.setdefault(key, []).append(row)
    lines = []
    for words in rows.values():
        confidence = sum(float(word["conf"]) for word in words) / len(words)
        top = min(int(word["top"]) for word in words)
        bottom = max(int(word["top"]) + int(word["height"]) for word in words)
        lines.append(CaptionLine(
            " ".join(word["text"].strip() for word in words),
            top, bottom - top, min(int(word["left"]) for word in words),
            confidence,
        ))
    return sorted(lines, key=lambda line: (line.top, line.left))


def split_speech(
    lines: list[CaptionLine], separate_speakers: bool, previous_speaker: str = ""
) -> list[Speech]:
    speech = []
    if lines:
        if not separate_speakers:
            text = " ".join(
                line.text for line in lines
                if line.confidence >= MIN_LINE_CONFIDENCE
                and re.search(r"[A-Za-z]", line.text)
            )
            if text:
                speech.append(Speech("", text))
        else:
            account_rows = {
                index for index, line in enumerate(lines)
                if ACCOUNT_LABEL.fullmatch(line.text.strip())
            }
            headings = account_rows
            if not headings:
                body_height = max(line.height for line in lines)
                headings = {0}
                for index, line in enumerate(lines[1:], 1):
                    words = line.text.split()
                    name_shape = (
                        all(word[0].isupper() for word in words)
                        or bool(re.search(r"[_@\d]", line.text))
                    )
                    if (
                        line.height <= body_height * HEADER_HEIGHT_RATIO
                        and len(words) <= MAX_HEADER_WORDS and name_shape
                        and not sentence_end(words[-1])
                    ):
                        headings.add(index)
            speaker = previous_speaker
            body: list[str] = []
            for index, line in enumerate(lines):
                if index in headings:
                    if speaker:
                        append_speech(speech, speaker, body)
                    speaker = re.sub(r"\s+", "", line.text) if index in account_rows else line.text
                    body = []
                elif speaker and line.confidence >= MIN_LINE_CONFIDENCE:
                    body.append(line.text)
            if speaker:
                append_speech(speech, speaker, body)
    return speech


def append_speech(speech: list[Speech], speaker: str, body: list[str]) -> None:
    text = " ".join(body)
    if speech and speech[-1].speaker == speaker:
        text = " ".join(filter(None, (speech[-1].text, text)))
        speech[-1] = Speech(speaker, text)
    else:
        speech.append(Speech(speaker, text))


class SpeechBuffer:
    def __init__(self) -> None:
        self.buffers: OrderedDict[str, SentenceBuffer] = OrderedDict()
        self.active = ""
        self.finished: list[Speech] = []

    def observe(self, speech: list[Speech], now: float) -> None:
        speaking = [item for item in speech if item.text]
        if speaking:
            latest = speaking[-1].speaker
            if latest != self.active and self.active in self.buffers:
                text = self.buffers[self.active].finish(now)
                if text:
                    self.finished.append(Speech(self.active, text))
            self.active = latest
        for item in speech:
            if item.text:
                if item.speaker not in self.buffers:
                    self.buffers[item.speaker] = SentenceBuffer()
                self.buffers.move_to_end(item.speaker)
                self.buffers[item.speaker].observe(item.text, now)
        visible = {item.speaker for item in speaking}
        for speaker, buffer in self.buffers.items():
            if speaker not in visible:
                buffer.observe("", now)
        while len(self.buffers) > MAX_SPEAKERS:
            self.buffers.popitem(last=False)

    def take(self, now: float) -> list[Speech]:
        result = self.finished
        self.finished = []
        clear = False
        for speaker, buffer in self.buffers.items():
            text = buffer.take(now)
            if text:
                result.append(Speech(speaker, text))
            elif text == "" and speaker == self.active:
                clear = True
        if clear and not result:
            result.append(Speech("", ""))
        return result


def display_translation(speech: Speech, translated: str) -> str:
    text = translated
    if speech.speaker and translated:
        text = speech.speaker + "\n" + translated
    return text


def translate_speech(speech: Speech, translate: Callable[[str], str]) -> str:
    return display_translation(speech, translate(speech.text))
