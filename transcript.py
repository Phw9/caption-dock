"""Keep ordered utterances and replace live previews without losing history."""
from collections import OrderedDict
from dataclasses import dataclass
from difflib import SequenceMatcher

from captions import (CLEAR_SECONDS, HISTORY_WORDS, MAX_PENDING_SECONDS, MAX_SENTENCE_WORDS,
                      QUIET_SECONDS, SETTLE_SECONDS, sentence_end, word_key)
from speech import Speech

MAX_TRANSCRIPT_ROWS = 100
MIN_SHARED_WORDS = 3


@dataclass(frozen=True)
class Word:
    speaker: str
    text: str


@dataclass(frozen=True)
class CaptionRequest:
    identifier: int
    speech: Speech
    observed_at: float


@dataclass
class PendingSentence:
    speech: Speech
    changed_at: float
    started_at: float
    observed_at: float
    emitted: str = ""


@dataclass
class TranscriptEntry:
    request: CaptionRequest
    translated: str = ""


def token_offset(previous: list[Word], current: list[Word]) -> int:
    old = [(word.speaker, word_key(word.text)) for word in previous]
    new = [(word.speaker, word_key(word.text)) for word in current]
    limit = min(len(old), len(new))
    prefix = 0
    while prefix < limit and old[prefix] == new[prefix]:
        prefix += 1
    overlap = 0
    for size in range(limit, 0, -1):
        if old[-size:] == new[:size] and (size > 1 or not sentence_end(previous[-1].text)):
            overlap = size
            break
    offset = len(old) - overlap
    if prefix >= overlap and (prefix >= 2 or prefix == limit > 0):
        offset = 0
    match = SequenceMatcher(None, old, new, autojunk=False).find_longest_match()
    if match.size >= MIN_SHARED_WORDS and (
        match.a + match.size == len(old) or match.b + match.size == len(new)
    ):
        offset = match.a - match.b
    return offset


class TranscriptBuffer:
    def __init__(self) -> None:
        self.words: list[Word] = []
        self.previous: list[Word] = []
        self.previous_start = 0
        self.committed = 0
        self.base = 0
        self.blank_at: float | None = None
        self.pending: dict[int, PendingSentence] = {}

    def observe(self, speech: list[Speech], now: float, captured_at: float | None = None) -> None:
        current = [Word(item.speaker, word) for item in speech for word in item.text.split()]
        current = current[-HISTORY_WORDS:]
        if current:
            if self.blank_at is not None and now - self.blank_at >= CLEAR_SECONDS:
                self.previous = []
                self.previous_start = len(self.words)
            self.blank_at = None
            if current != self.previous:
                start = max(0, self.previous_start + token_offset(self.previous, current))
                consumed = min(max(0, self.committed - start), len(current))
                old = [(word.speaker, word_key(word.text)) for word in self.previous]
                new = [(word.speaker, word_key(word.text)) for word in current]
                mismatch = new[:consumed] != [
                    (word.speaker, word_key(word.text))
                    for word in self.words[start:start + consumed]
                ]
                if mismatch:
                    match = SequenceMatcher(None, old, new, autojunk=False).find_longest_match()
                    shared = match.size >= MIN_SHARED_WORDS and (
                        match.a + match.size == len(old) or match.b + match.size == len(new)
                    )
                    if not shared:
                        start = len(self.words)
                keep = max(start, self.committed)
                self.words = self.words[:keep] + current[keep - start:]
                self.previous = current
                self.previous_start = start
                self.refresh(now, now if captured_at is None else captured_at)
        elif self.blank_at is None:
            self.blank_at = now

    def segments(self) -> list[tuple[int, list[Word], bool]]:
        result = []
        start = self.committed
        while start < len(self.words):
            end = start
            closed = False
            while end < len(self.words):
                if self.words[end].speaker != self.words[start].speaker:
                    closed = True
                    break
                end += 1
                if sentence_end(self.words[end - 1].text) or end - start >= MAX_SENTENCE_WORDS:
                    closed = True
                    break
            result.append((start, self.words[start:end], closed))
            start = end
        return result

    def refresh(self, now: float, captured_at: float) -> None:
        visible = set()
        for start, words, _closed in self.segments():
            identifier = self.base + start
            visible.add(identifier)
            speech = Speech(words[0].speaker, " ".join(word.text for word in words))
            state = self.pending.get(identifier)
            if state is None:
                self.pending[identifier] = PendingSentence(speech, now, now, captured_at)
            elif state.speech != speech:
                state.speech = speech
                state.changed_at = now
                state.observed_at = captured_at
        self.pending = {key: state for key, state in self.pending.items() if key in visible}

    def take(self, now: float) -> list[CaptionRequest]:
        result = []
        for start, words, closed in self.segments():
            identifier = self.base + start
            state = self.pending[identifier]
            quiet = now - state.changed_at >= QUIET_SECONDS
            final = (
                (closed and now - state.changed_at >= SETTLE_SECONDS)
                or now - state.started_at >= MAX_PENDING_SECONDS
                or (self.blank_at is not None and quiet)
            )
            if final or quiet:
                if state.emitted != state.speech.text:
                    result.append(CaptionRequest(identifier, state.speech, state.observed_at))
                    state.emitted = state.speech.text
                if final:
                    self.committed = start + len(words)
                    del self.pending[identifier]
            if not final:
                break
        drop = min(max(0, self.committed - HISTORY_WORDS), self.previous_start)
        if drop:
            self.words = self.words[drop:]
            self.committed -= drop
            self.previous_start -= drop
            self.base += drop
        return result


class TranscriptHistory:
    def __init__(self) -> None:
        self.rows: OrderedDict[int, TranscriptEntry] = OrderedDict()

    def pending(self, request: CaptionRequest) -> None:
        entry = self.rows.get(request.identifier)
        if entry is None:
            self.rows[request.identifier] = TranscriptEntry(request)
        else:
            entry.request = request
        while len(self.rows) > MAX_TRANSCRIPT_ROWS:
            self.rows.popitem(last=False)

    def translated(self, request: CaptionRequest, text: str) -> bool:
        entry = self.rows.get(request.identifier)
        accepted = entry is not None and entry.request.speech == request.speech
        if accepted:
            entry.translated = text
        return accepted

    def clear(self) -> None:
        self.rows.clear()
