from __future__ import annotations

from local_tts.engine.base import EngineHealth, TTSEngine
from local_tts.models import SynthesisResult


class MockTTSEngine(TTSEngine):
    """Deterministic Phase 2 engine; it never loads a model or accesses audio files."""

    def __init__(self, supported_voice_ids: list[str] | None = None) -> None:
        self._supported_voice_ids = sorted(set(supported_voice_ids or []))
        self.calls: list[tuple[str, str, float]] = []

    def health(self) -> EngineHealth:
        return EngineHealth("READY", "mock engine")

    def list_voices(self) -> list[str]:
        return list(self._supported_voice_ids)

    def synthesize(self, text: str, voice_id: str, speed: float = 1.0) -> SynthesisResult:
        if voice_id not in self._supported_voice_ids:
            raise ValueError(f"Mock engine does not support '{voice_id}'")
        if not text.strip():
            raise ValueError("text must not be blank")
        if speed <= 0:
            raise ValueError("speed must be positive")
        self.calls.append((text, voice_id, speed))
        return SynthesisResult(b"RIFFMOCK", 48_000, voice_id)
