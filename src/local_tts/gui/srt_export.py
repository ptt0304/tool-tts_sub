from __future__ import annotations

from pathlib import Path
from typing import Callable

from local_tts.gui.srt import SRTCue
from local_tts.service import TTSService


def generate_srt_audio(service: TTSService, cues: list[SRTCue], voice_id: str, output_dir: Path, speed: float = 1.0, progress: Callable[[int, int, SRTCue], None] | None = None) -> list[Path]:
    """Generate one WAV per SRT cue. Placement and mixing remain client-owned."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for position, cue in enumerate(cues, start=1):
        result = service.synthesize(cue.text, voice_id, speed)
        target = output_dir / f"srt_{cue.index:06d}.wav"
        target.write_bytes(result.wav_bytes)
        outputs.append(target)
        if progress:
            progress(position, len(cues), cue)
    return outputs
