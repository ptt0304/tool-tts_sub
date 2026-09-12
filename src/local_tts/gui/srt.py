from __future__ import annotations

from dataclasses import dataclass
import re


_TIMESTAMP = re.compile(r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}[,.]\d{3}")


@dataclass(frozen=True, slots=True)
class SRTCue:
    index: int
    start: str
    end: str
    text: str


def parse_srt(content: str) -> list[SRTCue]:
    """Parse standard SRT blocks while preserving cue text and timestamps."""
    cues: list[SRTCue] = []
    for block in re.split(r"\r?\n\s*\r?\n", content.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        timestamp_at = 1 if lines[0].isdigit() else 0
        if timestamp_at >= len(lines) or not _TIMESTAMP.match(lines[timestamp_at]):
            continue
        start, end = (part.strip() for part in lines[timestamp_at].split("-->", 1))
        text = "\n".join(lines[timestamp_at + 1:]).strip()
        if text:
            cue_number = int(lines[0]) if timestamp_at else len(cues) + 1
            cues.append(SRTCue(cue_number, start, end, text))
    return cues
