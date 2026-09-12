from __future__ import annotations

from pathlib import Path

from local_tts.models import Voice
from local_tts.voice.zk_importer import VoiceImportResult, ZKVoiceImporter


class VoiceRegistry:
    """Registry metadata only; it does not initialize a TTS engine."""

    def __init__(self, voices: list[Voice]) -> None:
        self._voices = {voice.voice_id: voice for voice in voices}
        if len(self._voices) != len(voices):
            raise ValueError("voice_id values must be unique")

    @classmethod
    def from_zk_directory(cls, root: Path, importer: ZKVoiceImporter | None = None) -> tuple["VoiceRegistry", VoiceImportResult]:
        result = (importer or ZKVoiceImporter()).import_directory(root)
        return cls(result.voices), result

    def list(self) -> list[Voice]:
        return sorted(self._voices.values(), key=lambda voice: voice.voice_id)

    def get(self, voice_id: str) -> Voice | None:
        return self._voices.get(voice_id)

    def replace(self, voice: Voice) -> None:
        """Replace one registered voice while preserving its stable ID."""
        if voice.voice_id not in self._voices:
            raise KeyError(voice.voice_id)
        self._voices[voice.voice_id] = voice
