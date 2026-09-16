from __future__ import annotations

import io
import logging
import math
import time
import wave
from array import array
from collections import deque
from dataclasses import dataclass
from typing import Callable

from local_tts.models import SynthesisResult
from local_tts.text_chunking import ChunkingSettings, TextChunk, estimate_syllables, plan_text_chunks


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


_EDGE_SILENCE_AMPLITUDE = 128  # approximately -48 dBFS for signed 16-bit PCM
_EDGE_MARGIN_SECONDS = 0.012
_FADE_SECONDS = 0.006


def _pause_for(chunk: TextChunk, settings: PauseSettings) -> float:
    if chunk.boundary_after.endswith("_newline"):
        base_boundary = chunk.boundary_after.removesuffix("_newline")
        return max(_pause_for(TextChunk("", 0, base_boundary, "", 0), settings), settings.newline)
    return {
        "break": settings.break_time,
        "newline": settings.newline,
        "ellipsis": settings.ellipsis,
        "question": settings.question,
        "exclamation": settings.period,
        "sentence": settings.period,
        "colon": settings.colon,
        "comma": settings.comma,
        "phrase": settings.space,
        "none": 0.0,
    }.get(chunk.boundary_after, 0.0)


def _decode_wav(data: bytes) -> tuple[wave._wave_params, bytes]:
    with wave.open(io.BytesIO(data), "rb") as reader:
        params = reader.getparams()
        if params.comptype != "NONE":
            raise ValueError("Only uncompressed PCM WAV output is supported")
        return params, reader.readframes(reader.getnframes())


def _normalize_chunk_edges(
    audio_frames: bytes,
    params: wave._wave_params,
    desired_trailing_silence: float = 0.0,
) -> tuple[bytes, float, float]:
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
    natural_trailing = frame_count - last - 1
    retained_trailing = min(
        natural_trailing,
        max(margin, round(desired_trailing_silence * params.framerate)),
    )
    end = min(frame_count, last + 1 + retained_trailing)
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


def _trailing_silence_seconds(audio_frames: bytes, params: wave._wave_params) -> float:
    if params.sampwidth != 2 or not audio_frames:
        return 0.0
    samples = array("h")
    samples.frombytes(audio_frames)
    channels = params.nchannels
    frame_count = len(samples) // channels
    last_active = next(
        (
            frame for frame in range(frame_count - 1, -1, -1)
            if any(abs(samples[frame * channels + channel]) > _EDGE_SILENCE_AMPLITUDE for channel in range(channels))
        ),
        None,
    )
    if last_active is None:
        return 0.0
    return (frame_count - last_active - 1) / params.framerate


def _append_crossfaded(
    destination: bytearray,
    audio_frames: bytes,
    params: wave._wave_params,
    crossfade_ms: int,
) -> None:
    """Join PCM16 chunks inside their retained silent edge margins."""
    frame_width = params.nchannels * params.sampwidth
    overlap_frames = min(
        round(crossfade_ms / 1000 * params.framerate),
        len(destination) // frame_width,
        len(audio_frames) // frame_width,
    )
    if not destination or not overlap_frames or params.sampwidth != 2:
        destination.extend(audio_frames)
        return
    overlap_bytes = overlap_frames * frame_width
    previous = array("h")
    incoming = array("h")
    previous.frombytes(destination[-overlap_bytes:])
    incoming.frombytes(audio_frames[:overlap_bytes])
    channels = params.nchannels
    for frame in range(overlap_frames):
        incoming_gain = (frame + 1) / (overlap_frames + 1)
        previous_gain = 1.0 - incoming_gain
        for channel in range(channels):
            index = frame * channels + channel
            mixed = round(previous[index] * previous_gain + incoming[index] * incoming_gain)
            previous[index] = max(-32768, min(32767, mixed))
    destination[-overlap_bytes:] = previous.tobytes()
    destination.extend(audio_frames[overlap_bytes:])
    logger.info("SYNTH crossfade=%dms overlap_frames=%d", crossfade_ms, overlap_frames)


def _retry_chunks(text: str) -> list[str]:
    """Find semantic fallback boundaries after a provider rejects a chunk."""
    syllables = estimate_syllables(text)
    if syllables < 8:
        return []
    hard_max = max(4, syllables // 2)
    preferred = min(16, hard_max)
    minimum = min(3, preferred)
    planned = plan_text_chunks(
        text,
        ChunkingSettings(
            preferred_syllables=preferred,
            soft_max_syllables=hard_max,
            hard_max_syllables=hard_max,
            minimum_chunk_syllables=minimum,
        ),
    )
    return [chunk.text for chunk in planned] if len(planned) > 1 else []


def synthesize_with_pauses(
    synthesize: Callable[[str], SynthesisResult],
    text: str,
    settings: PauseSettings,
    chunking: ChunkingSettings | None = None,
) -> SynthesisResult:
    chunking = chunking or ChunkingSettings()
    planned = plan_text_chunks(text, chunking)
    chunks = [(chunk.text, _pause_for(chunk, settings)) for chunk in planned]
    if not chunks:
        raise ValueError("text must contain spoken content")
    started = time.perf_counter()
    first_result: SynthesisResult | None = None
    expected = None
    frames = bytearray()
    total_generation = 0.0
    completed_results: list[SynthesisResult] = []
    previous_pause_seconds: float | None = None

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
                retries = _retry_chunks(spoken) if "empty audio" in str(error).lower() else []
                if not retries:
                    raise
                logger.warning(
                    "SYNTH empty audio; retrying at %d semantic boundaries",
                    len(retries) - 1,
                )
                for index, retry in reversed(list(enumerate(retries))):
                    pending_chunks.appendleft((retry, pause_seconds if index == len(retries) - 1 else 0.0))
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
            # Normalize only excessive edge silence. The small retained margin
            # counts toward the requested pause, so it is never added twice.
            audio_frames, trimmed_leading, trimmed_trailing = _normalize_chunk_edges(
                audio_frames, params, pause_seconds
            )
            if trimmed_leading or trimmed_trailing:
                logger.info(
                    "SYNTH normalized edges leading=%.3fs trailing=%.3fs",
                    trimmed_leading,
                    trimmed_trailing,
                )
            if frames and previous_pause_seconds == 0:
                _append_crossfaded(frames, audio_frames, params, chunking.crossfade_ms)
            else:
                frames.extend(audio_frames)
            if pause_seconds:
                natural_pause = _trailing_silence_seconds(audio_frames, params)
                silent_frames = round(max(0.0, pause_seconds - natural_pause) * params.framerate)
                fill = b"\x80" if params.sampwidth == 1 else b"\x00"
                frames.extend(fill * silent_frames * params.nchannels * params.sampwidth)
            previous_pause_seconds = pause_seconds
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
