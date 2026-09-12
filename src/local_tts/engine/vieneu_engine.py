from __future__ import annotations

import threading
import time
import uuid
import json
from dataclasses import replace
from pathlib import Path

from local_tts.engine.base import EngineHealth, TTSEngine
from local_tts.models import SynthesisResult, VoiceCategory
from local_tts.voice import VoiceRegistry


class VieNeuEngine(TTSEngine):
    """One long-lived VieNeu v3 Turbo instance on the official CPU/ONNX path."""

    def __init__(
        self,
        registry: VoiceRegistry,
        output_dir: Path,
        *,
        precision: str = "fp32",
        threads: int = 0,
    ) -> None:
        if precision not in {"fp32", "int8"}:
            raise ValueError("precision must be fp32 or int8")
        self._registry = registry
        self._output_dir = output_dir
        self._precision = precision
        self._threads = threads
        self._tts = None
        self._startup_seconds: float | None = None
        self._failure: str | None = None
        self._lock = threading.RLock()
        self._reference_cache = {}

    @property
    def startup_seconds(self) -> float | None:
        return self._startup_seconds

    def start(self) -> None:
        """Load once. A failure is retained for health reporting and can be retried."""
        with self._lock:
            if self._tts is not None:
                return
            self._failure = None
            started = time.perf_counter()
            try:
                from vieneu import Vieneu

                self._tts = Vieneu(
                    mode="v3turbo",
                    backend="onnx",
                    device="cpu",
                    precision=self._precision,
                    threads=self._threads,
                )
                self._startup_seconds = time.perf_counter() - started
            except Exception as error:
                self._failure = str(error)
                raise

    def close(self) -> None:
        with self._lock:
            if self._tts is not None:
                self._tts.close()
                self._tts = None

    def health(self) -> EngineHealth:
        if self._tts is not None:
            return EngineHealth("READY", "VieNeu v3 Turbo ONNX/CPU")
        if self._failure:
            return EngineHealth("FAILED", self._failure)
        return EngineHealth("NOT_STARTED", "Call start() once during application startup")

    def list_voices(self) -> list[str]:
        return [voice.voice_id for voice in self._registry.list() if voice.engine.startswith("vieneu_v3")]

    def synthesize(self, text: str, voice_id: str, speed: float = 1.0) -> SynthesisResult:
        import math
        if not math.isfinite(speed) or not 0.25 <= speed <= 3.0:
            raise ValueError("speed must be between 0.25 and 3.0")
        if not text.strip():
            raise ValueError("text must not be blank")
        voice = self._registry.get(voice_id)
        if voice is None:
            raise KeyError(voice_id)
        if self._tts is None:
            raise RuntimeError("VieNeu engine has not been started")

        with self._lock:
            if self._tts is None:
                raise RuntimeError("VieNeu engine has not been started")
            started = time.perf_counter()
            if voice.category is VoiceCategory.PRESET:
                preset_name = voice.metadata["preset_name"]
                audio = self._tts.infer(text, voice=preset_name)
            elif voice.category is VoiceCategory.REFERENCE and voice.reference_audio:
                stat = voice.reference_audio.stat()
                key = (str(voice.reference_audio.resolve()), stat.st_size, stat.st_mtime_ns)
                if key not in self._reference_cache:
                    embedding, codes = self._tts.encode_reference(voice.reference_audio)
                    self._reference_cache[key] = {"speaker_emb": embedding, "codes": codes}
                audio = self._tts.infer(text, voice=self._reference_cache[key])
            else:
                raise ValueError(f"Voice '{voice_id}' is not a VieNeu preset or reference WAV")
            if speed != 1.0:
                import librosa
                audio = librosa.effects.time_stretch(audio, rate=speed)
            import numpy as np
            if not np.isfinite(audio).all():
                raise RuntimeError("VieNeu returned non-finite audio")
            generation_seconds = time.perf_counter() - started
            sample_rate = int(self._tts.sample_rate)
            audio_duration_seconds = len(audio) / sample_rate if len(audio) else 0.0
            if audio_duration_seconds <= 0:
                raise RuntimeError("VieNeu returned empty audio")
            self._output_dir.mkdir(parents=True, exist_ok=True)
            output_path = self._output_dir / f"{voice_id}_{uuid.uuid4().hex[:8]}.wav"
            self._tts.save(audio, str(output_path))
            telemetry = {
                "voice_id": voice_id,
                "generation_seconds": generation_seconds,
                "audio_duration_seconds": audio_duration_seconds,
                "rtf": generation_seconds / audio_duration_seconds,
                "sample_rate": sample_rate,
                "output_path": str(output_path),
            }
            output_path.with_suffix(".json").write_text(json.dumps(telemetry, indent=2), encoding="utf-8")
            return SynthesisResult(
                wav_bytes=output_path.read_bytes(),
                sample_rate=sample_rate,
                voice_id=voice_id,
                output_path=output_path,
                generation_seconds=generation_seconds,
                audio_duration_seconds=audio_duration_seconds,
                rtf=telemetry["rtf"],
            )


def smoke_registry(reference_voice) -> VoiceRegistry:
    """Return an in-memory registry for the two required POC voices only.

    `reference_voice` remains unverified in persistent registry data. This copy is
    enabled solely for the integration smoke test that establishes compatibility.
    """
    from local_tts.models import Voice, VoiceCategory, VoiceStatus

    preset = Voice(
        voice_id="vieneu_adam",
        display_name="Adam",
        source="VieNeu-TTS v3 Turbo built-in preset",
        engine="vieneu_v3",
        status=VoiceStatus.READY,
        category=VoiceCategory.PRESET,
        metadata={"preset_name": "Adam"},
    )
    return VoiceRegistry([preset, replace(reference_voice, status=VoiceStatus.READY)])
