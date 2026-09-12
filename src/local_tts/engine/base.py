from __future__ import annotations

from abc import ABC, abstractmethod

from dataclasses import dataclass

from local_tts.models import SynthesisResult


@dataclass(frozen=True, slots=True)
class EngineHealth:
    status: str
    detail: str | None = None


class TTSEngine(ABC):
    @abstractmethod
    def health(self) -> EngineHealth: ...

    @abstractmethod
    def list_voices(self) -> list[str]: ...

    @abstractmethod
    def synthesize(self, text: str, voice_id: str, speed: float = 1.0) -> SynthesisResult: ...
