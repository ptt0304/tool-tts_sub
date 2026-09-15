from __future__ import annotations

import io
import wave


PREVIEW_SECONDS = 10.0
PREVIEW_TEXT = (
    "Xin chào, bạn đang sử dụng công cụ TTS của Tùng, "
    "đây là phần nghe thử giọng nói tiếng Việt. "
    "Chúc bạn một ngày làm việc hiệu quả, vui vẻ và tràn đầy cảm hứng."
)


def fit_wav_duration(data: bytes, seconds: float = PREVIEW_SECONDS) -> bytes:
    """Crop or pad an uncompressed WAV to an exact duration."""
    if seconds <= 0:
        raise ValueError("preview duration must be positive")
    with wave.open(io.BytesIO(data), "rb") as reader:
        params = reader.getparams()
        if params.comptype != "NONE":
            raise ValueError("Only uncompressed PCM WAV output is supported")
        source_frames = reader.readframes(reader.getnframes())

    target_frames = round(seconds * params.framerate)
    frame_width = params.nchannels * params.sampwidth
    target_bytes = target_frames * frame_width
    frames = source_frames[:target_bytes]
    if len(frames) < target_bytes:
        fill = b"\x80" if params.sampwidth == 1 else b"\x00"
        frames += fill * (target_bytes - len(frames))

    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(params.nchannels)
        writer.setsampwidth(params.sampwidth)
        writer.setframerate(params.framerate)
        writer.writeframes(frames)
    return output.getvalue()
