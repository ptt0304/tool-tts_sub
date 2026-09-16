from __future__ import annotations

from local_tts.engine.base import EngineHealth, TTSEngine
from local_tts.models import SynthesisResult
from local_tts.voice import VoiceRegistry


class RoutingEngine(TTSEngine):
    """Route each registered voice to its owning synthesis backend."""

    def __init__(self, registry: VoiceRegistry, vieneu: TTSEngine, piper: TTSEngine | None = None) -> None:
        self._registry = registry
        self._vieneu = vieneu
        self._piper = piper

    def start(self) -> None:
        self._vieneu.start()
        try:
            if self._piper is not None:
                self._piper.start()
        except Exception:
            self._vieneu.close()
            raise

    def close(self) -> None:
        if self._piper is not None:
            self._piper.close()
        self._vieneu.close()

    def health(self) -> EngineHealth:
        engines = [self._vieneu] + ([self._piper] if self._piper is not None else [])
        health = [engine.health() for engine in engines]
        failed = next((item for item in health if item.status == "FAILED"), None)
        if failed:
            return failed
        if all(item.status == "READY" for item in health):
            return EngineHealth("READY", " + ".join(item.detail or "engine" for item in health))
        return next((item for item in health if item.status != "READY"), health[0])

    def list_voices(self) -> list[str]:
        voices = self._vieneu.list_voices()
        if self._piper is not None:
            voices.extend(self._piper.list_voices())
        return sorted(voices)

    def synthesize(self, text: str, voice_id: str, speed: float = 1.0) -> SynthesisResult:
        voice = self._registry.get(voice_id)
        if voice is None:
            raise KeyError(voice_id)
        if voice.engine == "piper":
            if self._piper is None:
                raise RuntimeError("Piper engine is not configured")
            return self._piper.synthesize(text, voice_id, speed)
        if voice.engine.startswith("vieneu_v3"):
            return self._vieneu.synthesize(text, voice_id, speed)
        raise ValueError(f"Voice '{voice_id}' uses unsupported engine '{voice.engine}'")
