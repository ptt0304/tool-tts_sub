from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class VoiceCategory(StrEnum):
    PRESET = "PRESET"
    REFERENCE = "REFERENCE"
    FIXED_MODEL = "FIXED_MODEL"


class VoiceStatus(StrEnum):
    READY = "READY"
    REQUIRES_REFERENCE = "REQUIRES_REFERENCE"
    UNSUPPORTED = "UNSUPPORTED"
    INVALID = "INVALID"
    DISABLED = "DISABLED"


@dataclass(frozen=True, slots=True)
class Voice:
    voice_id: str
    display_name: str
    status: VoiceStatus
    source: str
    engine: str
    reference_audio: Path | None = None
    reference_text: Path | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    category: VoiceCategory = VoiceCategory.REFERENCE
    status_reason: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "voice_id": self.voice_id,
            "display_name": self.display_name,
            "status": self.status,
            "source": self.source,
            "engine": self.engine,
            "status_reason": self.status_reason,
        }


# Retained as a transitional internal name while Phase 2 establishes Voice.
VoiceDefinition = Voice


@dataclass(frozen=True, slots=True)
class SynthesisResult:
    wav_bytes: bytes
    sample_rate: int
    voice_id: str
    output_path: Path | None = None
    generation_seconds: float | None = None
    audio_duration_seconds: float | None = None
    rtf: float | None = None
