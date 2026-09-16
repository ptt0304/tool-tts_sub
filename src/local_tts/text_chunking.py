from __future__ import annotations

import logging
import re
from dataclasses import dataclass


logger = logging.getLogger("local_tts.text_chunking")


@dataclass(frozen=True, slots=True)
class ChunkingSettings:
    """Soft linguistic constraints for Vietnamese-oriented TTS requests."""

    preferred_syllables: int = 16
    soft_max_syllables: int = 24
    hard_max_syllables: int = 32
    minimum_chunk_syllables: int = 3
    merge_short_sentences: bool = False
    crossfade_ms: int = 10

    def __post_init__(self) -> None:
        if not 1 <= self.minimum_chunk_syllables <= self.preferred_syllables:
            raise ValueError("minimum_chunk_syllables must be between 1 and preferred_syllables")
        if not self.preferred_syllables <= self.soft_max_syllables <= self.hard_max_syllables:
            raise ValueError("syllable limits must be ordered preferred <= soft <= hard")
        if not 0 <= self.crossfade_ms <= 30:
            raise ValueError("crossfade_ms must be between 0 and 30")


@dataclass(frozen=True, slots=True)
class TextChunk:
    text: str
    syllables: int
    boundary_after: str
    reason: str
    boundary_score: int


_SPOKEN_TOKEN = re.compile(r"[0-9A-Za-zÀ-ỹĐđ]+(?:[-'][0-9A-Za-zÀ-ỹĐđ]+)*", re.UNICODE)
_CONJUNCTION = re.compile(
    r"\b(?:tuy nhiên|thế nhưng|vì vậy|do đó|mặc dù|trước khi|sau khi|sau đó|"
    r"nhưng|mà|vì|nên|dù|nếu|thì|khi|rồi)\b",
    re.IGNORECASE,
)
_AUXILIARIES = {"đã", "đang", "sẽ", "vẫn", "cũng", "lại", "còn", "mới", "chưa", "không"}
_PREPOSITIONS = {"của", "cho", "với", "từ", "đến", "ở", "trong", "ngoài", "trước", "sau"}
_CLASSIFIERS = {"cái", "chiếc", "con", "người", "căn", "quyển", "cuốn", "tấm", "bộ", "đôi"}
_NUMBER_WORDS = {"một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín", "mười"}
_ABBREVIATIONS = {"tp", "ts", "ths", "pgs", "gs", "bs", "mr", "mrs", "ms", "dr", "stt"}


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n+ *", "\n", text)
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\?{2,}", "?", text)
    # Do not consume the whitespace after an ellipsis: it is needed by the
    # sentence segmenter to distinguish the following sentence.
    text = re.sub(r"(?:\.\s*){2,}\.", "...", text)
    return text.strip()


def estimate_syllables(text: str) -> int:
    # A whitespace-delimited spoken token is a useful, deterministic proxy for
    # Vietnamese syllables. Hyphenated abbreviations/names remain one unit.
    return len(_SPOKEN_TOKEN.findall(text))


def _sentence_segments(text: str) -> list[tuple[str, str]]:
    """Return complete sentences/paragraphs and their following boundary."""
    segments: list[tuple[str, str]] = []
    start = 0
    marker_pattern = r"\[break\]|(?:(?:\.{3}|…+|[.!?]+)[\"'”’]*)(?=\s|$)|\n+"
    for match in re.finditer(marker_pattern, text, re.IGNORECASE):
        marker = match.group(0)
        if marker.lower() == "[break]":
            spoken = text[start:match.start()].strip()
            if spoken:
                segments.append((spoken, "break"))
            elif segments:
                previous, _ = segments[-1]
                segments[-1] = (previous, "break")
            start = match.end()
            continue
        if "\n" in marker:
            spoken = text[start:match.start()].strip()
            if spoken:
                segments.append((spoken, "newline"))
            elif segments:
                previous, previous_boundary = segments[-1]
                segments[-1] = (previous, f"{previous_boundary}_newline")
            start = match.end()
            continue
        if marker.startswith(".") and not marker.startswith("..."):
            words_before = _SPOKEN_TOKEN.findall(text[start:match.start()])
            previous_raw = words_before[-1] if words_before else ""
            previous = previous_raw.lower()
            if previous in _ABBREVIATIONS or (len(previous_raw) == 1 and previous_raw.isupper()):
                continue
        spoken = text[start:match.end()].strip()
        if spoken:
            if "..." in marker or "…" in marker:
                boundary = "ellipsis"
            elif "?" in marker:
                boundary = "question"
            elif "!" in marker:
                boundary = "exclamation"
            else:
                boundary = "sentence"
            segments.append((spoken, boundary))
        start = match.end()
    remainder = text[start:].strip()
    if remainder:
        segments.append((remainder, "none"))
    return segments


def _tokens_around(text: str, position: int) -> tuple[str, str]:
    left = _SPOKEN_TOKEN.findall(text[:position])
    right = _SPOKEN_TOKEN.findall(text[position:])
    return (left[-1].lower() if left else "", right[0].lower() if right else "")


def _candidate_score(text: str, position: int, base: int, settings: ChunkingSettings) -> int:
    left_count = estimate_syllables(text[:position])
    right_count = estimate_syllables(text[position:])
    length_score = max(0, 30 - abs(left_count - settings.preferred_syllables) * 3)
    penalty = 0
    left, right = _tokens_around(text, position)
    if left in _AUXILIARIES:
        penalty += 70
    if left in _PREPOSITIONS:
        penalty += 60
    if left in _NUMBER_WORDS and right in _CLASSIFIERS:
        penalty += 100
    if left.isdigit() and right and (right in _CLASSIFIERS or len(right) <= 4):
        penalty += 100
    if min(left_count, right_count) < settings.minimum_chunk_syllables:
        penalty += 80
    return base + length_score - penalty


def _best_split(text: str, settings: ChunkingSettings) -> tuple[int, str, int] | None:
    candidates: dict[int, tuple[str, int]] = {}
    for match in re.finditer(r"[;:]\s*", text):
        candidates[match.end()] = ("strong_clause", 80)
    for match in re.finditer(r",\s*", text):
        candidates[match.end()] = ("comma", 60)
    for match in _CONJUNCTION.finditer(text):
        candidates.setdefault(match.start(), ("conjunction", 55))
    # Last-resort phrase boundaries are still word boundaries, never a hard
    # character or every-N-syllable cut.
    for match in re.finditer(r"\s+", text):
        candidates.setdefault(match.end(), ("phrase", 30))
    scored = [
        (_candidate_score(text, position, base, settings), position, reason)
        for position, (reason, base) in candidates.items()
        if text[:position].strip() and text[position:].strip()
    ]
    if not scored:
        return None
    score, position, reason = max(scored, key=lambda item: (item[0], -abs(estimate_syllables(text[:item[1]]) - settings.preferred_syllables)))
    return position, reason, score


def _split_long_sentence(text: str, boundary: str, settings: ChunkingSettings) -> list[TextChunk]:
    if estimate_syllables(text) <= settings.hard_max_syllables:
        sentence_boundaries = {"sentence", "question", "exclamation", "ellipsis", "newline", "break", "none"}
        reason = "complete_sentence" if boundary in sentence_boundaries or boundary.endswith("_newline") else boundary
        boundary_scores = {"colon": 80, "comma": 60, "phrase": 30}
        return [TextChunk(text, estimate_syllables(text), boundary, reason, boundary_scores.get(boundary, 100))]
    split = _best_split(text, settings)
    if split is None:
        return [TextChunk(text, estimate_syllables(text), boundary, "no_safe_boundary", 0)]
    position, reason, score = split
    left, right = text[:position].strip(), text[position:].strip()
    left_boundary = "colon" if left.endswith((":", ";")) else "comma" if left.endswith(",") else "phrase"
    return [
        *_split_long_sentence(left, left_boundary, settings),
        *_split_long_sentence(right, boundary, settings),
    ]


def plan_text_chunks(text: str, settings: ChunkingSettings | None = None) -> list[TextChunk]:
    settings = settings or ChunkingSettings()
    normalized = normalize_text(text)
    chunks: list[TextChunk] = []
    for sentence, boundary in _sentence_segments(normalized):
        chunks.extend(_split_long_sentence(sentence, boundary, settings))
    if settings.merge_short_sentences:
        merged: list[TextChunk] = []
        for chunk in chunks:
            if merged and merged[-1].boundary_after == "sentence" and merged[-1].syllables + chunk.syllables <= settings.soft_max_syllables:
                previous = merged.pop()
                joined = f"{previous.text} {chunk.text}"
                merged.append(TextChunk(joined, estimate_syllables(joined), chunk.boundary_after, "merged_short_sentences", 100))
            else:
                merged.append(chunk)
        chunks = merged
    for index, chunk in enumerate(chunks):
        logger.info(
            "CHUNK %d/%d syllables=%d reason=%s score=%d boundary=%s text=%r",
            index + 1, len(chunks), chunk.syllables, chunk.reason,
            chunk.boundary_score, chunk.boundary_after, chunk.text,
        )
    return chunks
