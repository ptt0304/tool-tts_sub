from __future__ import annotations

from local_tts.engine import TTSEngine
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from local_tts.models import SynthesisResult, VoiceCategory, VoiceStatus
from local_tts.voice import VoiceRegistry


class VoiceNotReadyError(ValueError):
    pass


class TTSService:
    def __init__(self, registry: VoiceRegistry, engine: TTSEngine, registry_path: Path | None = None) -> None:
        self.registry = registry
        self._engine = engine
        self._registry_path = registry_path
    def health(self):
        return self._engine.health()

    def list_voices(self):
        return self.registry.list()

    def synthesize(self, text: str, voice_id: str, speed: float = 1.0) -> SynthesisResult:
        voice = self.registry.get(voice_id)
        if voice is None:
            raise KeyError(voice_id)
        if voice.status is not VoiceStatus.READY:
            reason = voice.status_reason or voice.status
            raise VoiceNotReadyError(f"Voice '{voice_id}' is {reason}")
        return self._engine.synthesize(text, voice.voice_id, speed)

    def enable_reference_voice(self, voice_id: str) -> None:
        """Prove a selected ZK reference works before exposing it as READY."""
        voice = self.registry.get(voice_id)
        if voice is None:
            raise KeyError(voice_id)
        if voice.status is VoiceStatus.READY:
            return
        if voice.status is not VoiceStatus.DISABLED or voice.category is not VoiceCategory.REFERENCE:
            raise VoiceNotReadyError(f"Voice '{voice_id}' cannot be enabled")
        self._engine.synthesize("Xin chào.", voice_id)
        metadata = dict(voice.metadata)
        metadata["last_enabled_at"] = datetime.now(UTC).isoformat()
        metadata["validation_backend"] = "v3turbo/onnx/cpu"
        self.registry.replace(replace(voice, status=VoiceStatus.READY, status_reason=None, metadata=metadata))
        if self._registry_path:
            from local_tts.voice.validation import VoiceLibraryValidator
            VoiceLibraryValidator.save(self._registry_path, self.registry.list())
