"""Assemble sentences from successive snapshots of a rolling caption area."""
import re

SETTLE_SECONDS = 0.25
QUIET_SECONDS = 1.8
MAX_PENDING_SECONDS = 8.0
CLEAR_SECONDS = 2.4
MAX_SENTENCE_WORDS = 48
HISTORY_WORDS = 96
ABBREVIATIONS = {"mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.",
                 "e.g.", "i.e.", "vs.", "etc.", "a.m.", "p.m."}


def word_key(word: str) -> str:
    return re.sub(r"^\W+|\W+$", "", word).casefold()


def sentence_end(word: str) -> bool:
    token = word.rstrip("\"'”’)]}")
    return bool(
        token.endswith(("!", "?"))
        or (
            token.endswith(".") and not token.endswith("...")
            and token.casefold() not in ABBREVIATIONS
            and re.fullmatch(r"(?:[A-Za-z]\.)+", token) is None
        )
    )


def align(previous: list[str], current: list[str]) -> int:
    """Find where the new snapshot starts relative to the previous one."""
    old = [word_key(word) for word in previous]
    new = [word_key(word) for word in current]
    limit = min(len(old), len(new))
    prefix = 0
    while prefix < limit and old[prefix] and old[prefix] == new[prefix]:
        prefix += 1
    overlap = 0
    for size in range(limit, 0, -1):
        if old[-size:] == new[:size] and all(new[:size]):
            if size > 1 or not sentence_end(previous[-1]):
                overlap = size
                break
    offset = len(old) - overlap
    if prefix >= overlap and (prefix >= 2 or prefix == limit > 0):
        offset = 0
    return offset


class SentenceBuffer:
    def __init__(self) -> None:
        self.words: list[str] = []
        self.previous: list[str] = []
        self.committed = 0
        self.previous_start = 0
        self.changed_at = 0.0
        self.started_at: float | None = None
        self.blank_at: float | None = None
        self.complete: list[str] = []
        self.preview: list[str] = []
        self.completed_at = 0.0

    def observe(self, text: str, now: float) -> None:
        current = text.split()[-HISTORY_WORDS:]
        if not current:
            if self.blank_at is None:
                self.blank_at = now
        else:
            self.blank_at = None
            if current != self.previous:
                start = self.previous_start + align(self.previous, current)
                consumed = min(max(0, self.committed - start), len(current))
                if [word_key(word) for word in current[:consumed]] != [
                    word_key(word) for word in self.words[start:start + consumed]
                ]:
                    start = len(self.words)
                keep = max(start, self.committed)
                updated = self.words[:keep] + current[keep - start:]
                if updated != self.words:
                    self.words = updated
                    self.changed_at = now
                    self.refresh_complete(now)
                self.previous = current
                self.previous_start = start
                if self.committed < len(self.words) and self.started_at is None:
                    self.started_at = now
                elif self.committed == len(self.words):
                    self.started_at = None
                    self.preview.clear()
                self.trim_history()

    def refresh_complete(self, now: float) -> None:
        pending = self.words[self.committed:self.committed + MAX_SENTENCE_WORDS]
        complete = []
        for index, word in enumerate(pending, 1):
            if sentence_end(word):
                complete = pending[:index]
                break
        if complete != self.complete:
            self.complete = complete
            self.completed_at = now

    def trim_history(self) -> None:
        # Keep enough committed context to recognize overlapping windows.
        drop = min(max(0, self.committed - HISTORY_WORDS), self.previous_start)
        if drop:
            self.words = self.words[drop:]
            self.committed -= drop
            self.previous_start -= drop

    def finish(self, now: float) -> str | None:
        pending = self.words[self.committed:]
        result = None
        if pending:
            if pending != self.preview:
                result = " ".join(pending)
            self.committed = len(self.words)
            self.preview.clear()
            self.started_at = None
            self.refresh_complete(now)
            self.trim_history()
        return result

    def take(self, now: float) -> str | None:
        result = None
        pending = self.words[self.committed:]
        if pending:
            end = 0
            quiet = now - self.changed_at >= QUIET_SECONDS
            if self.complete and now - self.completed_at >= SETTLE_SECONDS:
                end = len(self.complete)
            if not end and (
                len(pending) >= MAX_SENTENCE_WORDS
                or (self.blank_at is not None and quiet)
                or (
                    self.started_at is not None
                    and now - self.started_at >= MAX_PENDING_SECONDS
                )
            ):
                end = min(len(pending), MAX_SENTENCE_WORDS)
            if end:
                if pending[:end] != self.preview:
                    result = " ".join(pending[:end])
                self.committed += end
                self.preview.clear()
                self.started_at = now if self.committed < len(self.words) else None
                self.refresh_complete(now)
                self.trim_history()
            elif quiet and pending != self.preview:
                self.preview = pending
                result = " ".join(pending)
        elif self.blank_at is not None and now - self.blank_at >= CLEAR_SECONDS:
            self.words.clear()
            self.previous.clear()
            self.committed = self.previous_start = 0
            self.started_at = self.blank_at = None
            result = ""
        return result
