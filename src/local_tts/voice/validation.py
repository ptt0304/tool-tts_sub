from __future__ import annotations

import json
import wave
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from local_tts.models import Voice, VoiceStatus


class VoiceLibraryValidator:
    def validate_incremental(self, voices, registry_path, infer=False, limit=1):
        previous = {}
        if registry_path.exists():
            previous = {r["voice_id"]: r for r in json.loads(registry_path.read_text(encoding="utf-8"))["voices"]}
        validated = self.validate_files(voices)
        attempts = 0
        engine = None
        try:
            for index, voice in enumerate(validated):
                old = previous.get(voice.voice_id, {})
                fingerprint = []
                for path in (voice.reference_audio, voice.reference_text):
                    fingerprint.append([str(path), path.stat().st_size, path.stat().st_mtime_ns] if path and path.is_file() else None)
                signature = json.dumps(fingerprint)
                voice.metadata["fingerprint"] = signature
                if old.get("metadata", {}).get("fingerprint") == signature and old.get("status") == "READY":
                    validated[index] = replace(voice, status=VoiceStatus.READY, status_reason=None, metadata=old["metadata"])
                    continue
                if infer and attempts < limit and voice.status is VoiceStatus.DISABLED:
                    if engine is None:
                        from local_tts.engine import VieNeuEngine
                        from local_tts.voice.registry import VoiceRegistry
                        engine = VieNeuEngine(VoiceRegistry(validated), registry_path.parent.parent / "outputs" / "validation")
                        engine.start()
                    attempts += 1
                    try:
                        result = engine.synthesize("Xin chào, chúc bạn một ngày tốt lành.", voice.voice_id)
                        import io
                        import soundfile as sf
                        import numpy as np
                        audio, rate = sf.read(io.BytesIO(result.wav_bytes))
                        if audio.size == 0 or not np.isfinite(audio).all() or np.max(np.abs(audio)) == 0:
                            raise ValueError("invalid_generated_audio")
                        voice.metadata.update({"inference_output": str(result.output_path), "inference_backend": "v3turbo/onnx/fp32", "review": "automated_audio_validation"})
                        validated[index] = replace(voice, status=VoiceStatus.READY, status_reason=None)
                    except Exception as error:
                        voice.metadata["validation_error"] = str(error)
                        validated[index] = replace(voice, status=VoiceStatus.DISABLED, status_reason="inference_failed")
                self.save(registry_path, validated)
        finally:
            if engine is not None:
                engine.close()
        self.save(registry_path, validated)
        return validated

    def validate_files(self, voices: list[Voice]) -> list[Voice]:
        now = datetime.now(UTC).isoformat()
        validated: list[Voice] = []
        for voice in voices:
            metadata = dict(voice.metadata)
            metadata["last_validated_at"] = now
            if not voice.reference_audio or not voice.reference_text or not voice.reference_audio.is_file() or not voice.reference_text.is_file():
                validated.append(replace(voice, status=VoiceStatus.INVALID, status_reason="missing_reference_pair", metadata=metadata))
                continue
            try:
                if not voice.reference_text.read_text(encoding="utf-8-sig").strip():
                    raise ValueError("empty_reference_text")
                with wave.open(str(voice.reference_audio), "rb") as audio:
                    duration = audio.getnframes() / audio.getframerate()
                if duration <= 0:
                    raise ValueError("zero_duration")
                metadata.update({"reference_duration_seconds": f"{duration:.3f}", "audio_size": str(voice.reference_audio.stat().st_size), "audio_mtime_ns": str(voice.reference_audio.stat().st_mtime_ns)})
                validated.append(replace(voice, status=VoiceStatus.DISABLED, status_reason="inference_not_run", metadata=metadata))
            except Exception as error:
                metadata["validation_error"] = str(error)
                validated.append(replace(voice, status=VoiceStatus.INVALID, status_reason="invalid_reference_audio", metadata=metadata))
        return validated

    @staticmethod
    def save(path: Path, voices: list[Voice]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        records = []
        for voice in voices:
            records.append({"voice_id": voice.voice_id, "display_name": voice.display_name, "source": voice.source, "engine": voice.engine, "status": voice.status, "reference_audio": str(voice.reference_audio) if voice.reference_audio else None, "reference_text": str(voice.reference_text) if voice.reference_text else None, "metadata": voice.metadata, "validation_error": voice.metadata.get("validation_error"), "last_validated_time": voice.metadata.get("last_validated_at")})
        for record, voice in zip(records, voices):
            record["status_reason"] = voice.status_reason
            record["reference_audio"] = str(voice.reference_audio.resolve()) if voice.reference_audio else None
            record["reference_text"] = str(voice.reference_text.resolve()) if voice.reference_text else None
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"voices": records}, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
