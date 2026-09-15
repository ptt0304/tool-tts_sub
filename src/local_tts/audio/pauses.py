from __future__ import annotations

import io
import logging
import math
import re
import time
import wave
from array import array
from collections import deque
from dataclasses import dataclass
from typing import Callable

from local_tts.models import SynthesisResult


logger = logging.getLogger("local_tts.audio.pauses")


@dataclass(frozen=True, slots=True)
class PauseSettings:
    space: float = 0.0
    comma: float = 0.25
    period: float = 0.45
    question: float = 0.55
    colon: float = 0.30
    ellipsis: float = 0.65
    newline: float = 0.50
    break_time: float = 1.0

    def __post_init__(self) -> None:
        for name, value in (
            ("space", self.space),
            ("comma", self.comma),
            ("period", self.period),
            ("question", self.question),
            ("colon", self.colon),
            ("ellipsis", self.ellipsis),
            ("newline", self.newline),
            ("break_time", self.break_time),
        ):
            if not math.isfinite(value) or not 0 <= value <= 10:
                raise ValueError(f"{name} must be between 0 and 10 seconds")


_IGNORED_QUOTES = re.compile(r'''['"“”‘’]''')
_IGNORED_EXCLAMATIONS = re.compile(r"[!！]+")
_DELIMITER = re.compile(r"(\[break\]|\.{3,}|\r?\n+|[ \t\f\v]+|[,;:?]|\.)", re.IGNORECASE)
_EDGE_SILENCE_AMPLITUDE = 128  # approximately -48 dBFS for signed 16-bit PCM
_EDGE_MARGIN_SECONDS = 0.012
_FADE_SECONDS = 0.006


def _split(text: str, settings: PauseSettings) -> list[tuple[str, float]]:
    # Quotes are decoration and exclamation marks must not influence prosody.
    # Replacing ! with one space prevents adjacent words from being joined.
    text = _IGNORED_QUOTES.sub("", text)
    text = _IGNORED_EXCLAMATIONS.sub(" ", text)
    chunks: list[list[str | float]] = []
    pending = ""
    for part in _DELIMITER.split(text):
        if not part:
            continue
        if not _DELIMITER.fullmatch(part):
            pending += part
            continue

        lowered = part.lower()
        is_space = bool(re.fullmatch(r"[ \t\f\v]+", part))
        if is_space and settings.space == 0:
            if pending and not pending.endswith(" "):
                pending += " "
            continue
        if lowered == "[break]":
            pause = settings.break_time
        elif "\n" in part or "\r" in part:
            pause = settings.newline
        elif part.startswith("..."):
            pause = settings.ellipsis
        elif is_space:
            pause = settings.space
        elif part in {",", ";"}:
            pause = settings.comma if part == "," else settings.colon
        elif part == ":":
            pause = settings.colon
        elif part == "?":
            pause = settings.question
        else:
            pause = settings.period

        spoken = pending.strip()
        if spoken:
            # Let the model see the punctuation so it can produce the correct
            # Vietnamese cadence. Its generated edge silence is normalized later,
            # before the configured total pause is inserted.
            prosody_mark = ""
            if part.startswith("..."):
                prosody_mark = "..."
            elif part in {",", ";", ":", "?", "."}:
                prosody_mark = part
            chunks.append([spoken + prosody_mark, pause])
            pending = ""
        elif chunks and not is_space:
            chunks[-1][1] = max(float(chunks[-1][1]), pause)

    spoken = pending.strip()
    if spoken:
        chunks.append([spoken, 0.0])
    result = [(str(chunk), float(pause)) for chunk, pause in chunks]
    # VieNeu reference inference can return an empty waveform for very long
    # single requests. Keep each synthesis request bounded while preserving
    # the configured pause after the original punctuation boundary.
    bounded: list[tuple[str, float]] = []
    for spoken, pause in result:
        words = spoken.split()
        current: list[str] = []
        size = 0
        for word in words:
            if current and size + 1 + len(word) > 180:
                bounded.append((" ".join(current), 0.0))
                current, size = [], 0
            current.append(word)
            size += len(word) + (1 if len(current) > 1 else 0)
        if current:
            bounded.append((" ".join(current), pause))
    return bounded


def _decode_wav(data: bytes) -> tuple[wave._wave_params, bytes]:
    with wave.open(io.BytesIO(data), "rb") as reader:
        params = reader.getparams()
        if params.comptype != "NONE":
            raise ValueError("Only uncompressed PCM WAV output is supported")
        return params, reader.readframes(reader.getnframes())


def _normalize_chunk_edges(audio_frames: bytes, params: wave._wave_params) -> tuple[bytes, float, float]:
    """Remove model-added edge silence and soften the new boundaries.

    PauseSettings describes the total intended gap. Without this normalization,
    VieNeu's own trailing silence and our inserted pause are added together.
    """
    if params.sampwidth != 2 or not audio_frames:
        return audio_frames, 0.0, 0.0
    samples = array("h")
    samples.frombytes(audio_frames)
    channels = params.nchannels
    frame_count = len(samples) // channels
    if not frame_count:
        return audio_frames, 0.0, 0.0

    def active(frame: int) -> bool:
        offset = frame * channels
        return any(abs(samples[offset + channel]) > _EDGE_SILENCE_AMPLITUDE for channel in range(channels))

    first = next((frame for frame in range(frame_count) if active(frame)), None)
    if first is None:
        # Deterministic mock/silent clips remain intact; real empty output is
        # rejected by the engine before reaching this function.
        return audio_frames, 0.0, 0.0
    last = next(frame for frame in range(frame_count - 1, -1, -1) if active(frame))
    margin = round(_EDGE_MARGIN_SECONDS * params.framerate)
    start = max(0, first - margin)
    end = min(frame_count, last + 1 + margin)
    trimmed_leading = start / params.framerate
    trimmed_trailing = (frame_count - end) / params.framerate
    normalized = array("h", samples[start * channels:end * channels])

    fade_frames = min(round(_FADE_SECONDS * params.framerate), len(normalized) // channels // 2)
    if fade_frames:
        for frame in range(fade_frames):
            gain = (frame + 1) / fade_frames
            tail_gain = (fade_frames - frame) / fade_frames
            for channel in range(channels):
                head = frame * channels + channel
                tail = (len(normalized) // channels - fade_frames + frame) * channels + channel
                normalized[head] = round(normalized[head] * gain)
                normalized[tail] = round(normalized[tail] * tail_gain)
    return normalized.tobytes(), trimmed_leading, trimmed_trailing


def _bisect_spoken(text: str) -> tuple[str, str] | None:
    """Split a failed synthesis chunk near its midpoint without breaking words."""
    words = text.split()
    if len(words) < 2 or len(text) < 40:
        return None
    target = len(text) / 2
    size = 0
    split_at = 1
    for index, word in enumerate(words[:-1], start=1):
        size += len(word) + (1 if index > 1 else 0)
        split_at = index
        if size >= target:
            break
    return " ".join(words[:split_at]), " ".join(words[split_at:])


def synthesize_with_pauses(
    synthesize: Callable[[str], SynthesisResult],
    text: str,
    settings: PauseSettings,
) -> SynthesisResult:
    chunks = _split(text, settings)
    if not chunks:
        raise ValueError("text must contain spoken content")
    started = time.perf_counter()
    first_result: SynthesisResult | None = None
    expected = None
    frames = bytearray()
    total_generation = 0.0
    completed_results: list[SynthesisResult] = []

    def cleanup_outputs() -> None:
        for completed in completed_results:
            if completed.output_path:
                try:
                    completed.output_path.unlink(missing_ok=True)
                except OSError:
                    pass

    try:
        pending_chunks = deque(chunks)
        completed_count = 0
        while pending_chunks:
            spoken, pause_seconds = pending_chunks.popleft()
            logger.info(
                "SYNTH chunk %d chars=%d remaining=%d",
                completed_count + 1,
                len(spoken),
                len(pending_chunks),
            )
            try:
                result = synthesize(spoken)
            except RuntimeError as error:
                halves = _bisect_spoken(spoken) if "empty audio" in str(error).lower() else None
                if halves is None:
                    raise
                left, right = halves
                logger.warning(
                    "SYNTH empty audio; retrying chunk as chars=%d+%d",
                    len(left),
                    len(right),
                )
                pending_chunks.appendleft((right, pause_seconds))
                pending_chunks.appendleft((left, 0.0))
                continue
            completed_results.append(result)
            completed_count += 1
            params, audio_frames = _decode_wav(result.wav_bytes)
            signature = (params.nchannels, params.sampwidth, params.framerate, params.comptype)
            if expected is None:
                expected = signature
                first_result = result
            elif signature != expected:
                raise ValueError("TTS chunks returned incompatible WAV formats")
            audio_frames, trimmed_leading, trimmed_trailing = _normalize_chunk_edges(audio_frames, params)
            if trimmed_leading or trimmed_trailing:
                logger.info(
                    "SYNTH normalized edges leading=%.3fs trailing=%.3fs",
                    trimmed_leading,
                    trimmed_trailing,
                )
            frames.extend(audio_frames)
            if pause_seconds:
                silent_frames = round(pause_seconds * params.framerate)
                fill = b"\x80" if params.sampwidth == 1 else b"\x00"
                frames.extend(fill * silent_frames * params.nchannels * params.sampwidth)
            total_generation += result.generation_seconds or 0.0
    except Exception:
        cleanup_outputs()
        raise

    assert first_result is not None and expected is not None
    channels, sample_width, sample_rate, _ = expected
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(sample_width)
        writer.setframerate(sample_rate)
        writer.writeframes(frames)
    duration = len(frames) / (sample_rate * channels * sample_width)
    generation = total_generation or (time.perf_counter() - started)
    try:
        return SynthesisResult(
            wav_bytes=output.getvalue(),
            sample_rate=sample_rate,
            voice_id=first_result.voice_id,
            generation_seconds=generation,
            audio_duration_seconds=duration,
            rtf=generation / duration if duration else None,
        )
    finally:
        cleanup_outputs()
