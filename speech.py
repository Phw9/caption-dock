"""Preserve OCR rows and separate a Teams speaker heading from speech."""
from collections import OrderedDict
from dataclasses import dataclass
import csv
from difflib import SequenceMatcher
import io
import re
from collections.abc import Callable

from captions import SentenceBuffer
from captions import sentence_end

MIN_LINE_CONFIDENCE = 35
MAX_AVATAR_CONFIDENCE = 60
HEADER_HEIGHT_RATIO = 0.8
MAX_HEADER_WORDS = 8
MAX_SPEAKERS = 8
MAX_SPEAKER_LABEL = 32
TEXT_COLUMN_TOLERANCE = 6
ACCOUNT_SIMILARITY = 0.80
ACCOUNT_LABEL = re.compile(r"[\w.+-]+\s*@\s*[\w.-]+\.[A-Za-z]{2,}")
ACCOUNT_TOKEN = re.compile(r"[\w.+-]+\s*@\s*[\w.-]+")
ACCOUNT_FRAGMENT = re.compile(r"gmail|outlook|hotmail|[.]com\b|[.]net\b|[.]org\b", re.I)
TSV_COLUMNS = ("level", "page_num", "block_num", "par_num", "line_num",
               "word_num", "left", "top", "width", "height", "conf", "text")


@dataclass(frozen=True)
class CaptionWord:
    text: str
    top: int
    height: int
    left: int
    confidence: float


@dataclass(frozen=True)
class CaptionLine:
    text: str
    top: int
    height: int
    left: int = 0
    confidence: float = 100.0
    words: tuple[CaptionWord, ...] = ()


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
            tuple(CaptionWord(
                word["text"].strip(), int(word["top"]), int(word["height"]),
                int(word["left"]), float(word["conf"]),
            ) for word in words),
        ))
    return sorted(lines, key=lambda line: (line.top, line.left))


def account_column(line: CaptionLine) -> int | None:
    column = None
    match = ACCOUNT_LABEL.search(line.text) or ACCOUNT_TOKEN.search(line.text)
    if match and match.end() == len(line.text.rstrip()):
        prefix = []
        account_left = line.left
        offset = 0
        for word in line.words:
            if offset <= match.start() < offset + len(word.text):
                account_left = word.left
            elif offset < match.start():
                prefix.append(word)
            offset += len(word.text) + 1
        if match.start() == 0 or (prefix and all(
            word.confidence < MAX_AVATAR_CONFIDENCE for word in prefix
        )):
            column = account_left
    return column


def clean_teams_lines(lines: list[CaptionLine]) -> list[CaptionLine]:
    """Remove avatar tokens to the left of the repeated account column."""
    anchors = [column for line in lines if (column := account_column(line)) is not None]
    cleaned = lines
    if anchors:
        left = sorted(anchors)[len(anchors) // 2] - TEXT_COLUMN_TOLERANCE
        cleaned = []
        for line in lines:
            words = tuple(word for word in line.words if word.left >= left)
            if words:
                top = min(word.top for word in words)
                bottom = max(word.top + word.height for word in words)
                cleaned.append(CaptionLine(
                    " ".join(word.text for word in words), top, bottom - top,
                    min(word.left for word in words),
                    sum(word.confidence for word in words) / len(words), words,
                ))
            elif not line.words and line.left >= left:
                cleaned.append(line)
    return cleaned


def heading_speaker(
    line: CaptionLine, body_height: int, known: list[str], allow_names: bool
) -> str | None:
    text = line.text.strip()
    compact = re.sub(r"\s+", "", text)
    speaker = None
    if ACCOUNT_LABEL.fullmatch(text):
        speaker = compact
    else:
        words = text.split()
        small = line.height <= body_height * HEADER_HEIGHT_RATIO
        name_shape = bool(words) and (
            all(word[0].isupper() for word in words)
            or bool(re.search(r"[_@\d]|\w\.\w", text))
        )
        # A damaged account row must never enter the translation body.
        account_like = (len(words) == 1 or (small and len(words) <= 3)) and (
            "@" in compact or bool(ACCOUNT_FRAGMENT.search(compact))
        )
        identifier = allow_names and bool(
            re.fullmatch(r"[a-z\d]+[._][a-z\d._-]+", text)
        )
        short_name = (
            allow_names and small and 2 <= len(words) <= MAX_HEADER_WORDS
            and name_shape and not sentence_end(words[-1])
        )
        if account_like or identifier or short_name:
            speaker = "" if account_like else text
            for candidate in known:
                similarity = SequenceMatcher(
                    None, compact.casefold(), candidate.casefold()
                ).ratio()
                if similarity >= ACCOUNT_SIMILARITY:
                    speaker = candidate
                    break
    return speaker


def speaker_label(speaker: str) -> str:
    name = speaker.split("@", 1)[0].strip()
    if len(name) > MAX_SPEAKER_LABEL:
        name = name[:MAX_SPEAKER_LABEL - 3] + "…"
    return name


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
            lines = clean_teams_lines(lines)
            known = [re.sub(r"\s+", "", line.text) for line in lines
                     if ACCOUNT_LABEL.fullmatch(line.text.strip())]
            if previous_speaker:
                known.append(previous_speaker)
            account_mode = any(ACCOUNT_LABEL.fullmatch(name) for name in known)
            body_height = max((line.height for line in lines), default=0)
            headings = {index: name for index, line in enumerate(lines)
                        if (name := heading_speaker(
                            line, body_height, known, allow_names=not account_mode
                        )) is not None}
            speaker = previous_speaker
            body: list[str] = []
            first_heading = min(headings, default=len(lines))
            for index, line in enumerate(lines):
                if index in headings:
                    if speaker or body:
                        append_speech(speech, speaker, body)
                    speaker = headings[index]
                    body = []
                elif speaker or not headings or index > first_heading:
                    if line.confidence >= MIN_LINE_CONFIDENCE:
                        body.append(line.text)
            if speaker or body:
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


def translate_caption(speech: Speech, translate: Callable[[str], str]) -> Speech:
    return Speech(speech.speaker, translate(speech.text))
