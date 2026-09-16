from __future__ import annotations

import math
import os
import subprocess
import sys
import threading
import time
import uuid
import wave
from array import array
from pathlib import Path

from local_tts.engine.base import EngineHealth, TTSEngine
from local_tts.models import SynthesisResult
from local_tts.voice import VoiceRegistry


class PiperEngine(TTSEngine):
    """Run fixed Piper ONNX voices through the bundled Windows CLI."""

    OUTPUT_SAMPLE_RATE = 48_000

    def __init__(
        self,
        registry: VoiceRegistry,
        output_dir: Path,
        *,
        executable: Path,
        espeak_data: Path,
    ) -> None:
        self._registry = registry
        self._output_dir = output_dir
        self._executable = executable
        self._espeak_data = espeak_data
        self._ready = False
        self._failure: str | None = None
        self._lock = threading.RLock()

    def start(self) -> None:
        with self._lock:
            self._failure = None
            try:
                if not self._executable.is_file():
                    raise FileNotFoundError(f"Piper executable not found: {self._executable}")
                if not self._espeak_data.is_dir():
                    raise FileNotFoundError(f"Piper espeak data not found: {self._espeak_data}")
                for voice_id in self.list_voices():
                    voice = self._registry.get(voice_id)
                    if voice is None:
                        raise KeyError(voice_id)
                    model = Path(voice.metadata["model_path"])
                    config = Path(voice.metadata.get("config_path", f"{model}.json"))
                    if not model.is_file():
                        raise FileNotFoundError(f"Piper model not found: {model}")
                    if not config.is_file():
                        raise FileNotFoundError(f"Piper config not found: {config}")
                self._ready = True
            except Exception as error:
                self._ready = False
                self._failure = str(error)
                raise

    def close(self) -> None:
        self._ready = False

    def health(self) -> EngineHealth:
        if self._ready:
            return EngineHealth("READY", "Piper ONNX/CPU")
        if self._failure:
            return EngineHealth("FAILED", self._failure)
        return EngineHealth("NOT_STARTED", "Call start() once during application startup")

    def list_voices(self) -> list[str]:
        return [voice.voice_id for voice in self._registry.list() if voice.engine == "piper"]

    def synthesize(self, text: str, voice_id: str, speed: float = 1.0) -> SynthesisResult:
        if not math.isfinite(speed) or not 0.25 <= speed <= 3.0:
            raise ValueError("speed must be between 0.25 and 3.0")
        if not text.strip():
            raise ValueError("text must not be blank")
        voice = self._registry.get(voice_id)
        if voice is None:
            raise KeyError(voice_id)
        if voice.engine != "piper":
            raise ValueError(f"Voice '{voice_id}' is not a Piper voice")
        if not self._ready:
            raise RuntimeError("Piper engine has not been started")

        model = Path(voice.metadata["model_path"])
        config = Path(voice.metadata.get("config_path", f"{model}.json"))
        self._output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._output_dir / f"{voice_id}_{uuid.uuid4().hex[:8]}.wav"
        command = [
            str(self._executable),
            "--model", str(model),
            "--config", str(config),
            "--espeak_data", str(self._espeak_data),
            "--output_file", str(output_path),
            "--length_scale", str(1.0 / speed),
            "--quiet",
        ]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        started = time.perf_counter()
        with self._lock:
            try:
                completed = subprocess.run(
                    command,
                    input=(text.strip() + "\n").encode("utf-8"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    creationflags=creationflags,
                    timeout=120,
                )
                if completed.returncode != 0:
                    detail = completed.stderr.decode("utf-8", errors="replace").strip()
                    raise RuntimeError(f"Piper exited with code {completed.returncode}: {detail}")
                if not output_path.is_file() or output_path.stat().st_size <= 44:
                    raise RuntimeError("Piper did not create a valid WAV file")
                sample_rate, duration = self._normalize_wav(output_path)
                if duration <= 0:
                    raise RuntimeError("Piper returned empty audio")
            except Exception:
                output_path.unlink(missing_ok=True)
                raise

        generation_seconds = time.perf_counter() - started
        return SynthesisResult(
            wav_bytes=output_path.read_bytes(),
            sample_rate=sample_rate,
            voice_id=voice_id,
            output_path=output_path,
            generation_seconds=generation_seconds,
            audio_duration_seconds=duration,
            rtf=generation_seconds / duration,
        )

    @classmethod
    def _normalize_wav(cls, path: Path) -> tuple[int, float]:
        """Normalize Piper PCM16 output for VieNeu-compatible batch assembly."""
        with wave.open(str(path), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            source_rate = wav.getframerate()
            frame_count = wav.getnframes()
            frames = wav.readframes(frame_count)
        if channels != 1 or sample_width != 2 or source_rate <= 0:
            raise RuntimeError("Piper returned an unsupported WAV format")
        audio = array("h")
        audio.frombytes(frames)
        if sys.byteorder != "little":
            audio.byteswap()
        if not audio:
            raise RuntimeError("Piper returned empty audio")
        if source_rate != cls.OUTPUT_SAMPLE_RATE:
            target_size = max(1, round(len(audio) * cls.OUTPUT_SAMPLE_RATE / source_rate))
            resampled = array("h")
            scale = (len(audio) - 1) / max(1, target_size - 1)
            for target_index in range(target_size):
                position = target_index * scale
                left = int(position)
                right = min(left + 1, len(audio) - 1)
                fraction = position - left
                resampled.append(round(audio[left] + (audio[right] - audio[left]) * fraction))
            audio = resampled
        output_frames = array("h", audio)
        if sys.byteorder != "little":
            output_frames.byteswap()
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(cls.OUTPUT_SAMPLE_RATE)
            wav.writeframes(output_frames.tobytes())
        return cls.OUTPUT_SAMPLE_RATE, len(audio) / cls.OUTPUT_SAMPLE_RATE
