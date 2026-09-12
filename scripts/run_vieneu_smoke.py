"""Run the two-voice Phase 3 CPU/ONNX proof of concept.

Run with Local_TTS/src and VieNeu-TTS/src on PYTHONPATH. This is intentionally
not a user-facing voice cloning workflow.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from local_tts.engine.vieneu_engine import VieNeuEngine, smoke_registry
from local_tts.voice import ZKVoiceImporter


def main() -> None:
    voice_root = Path(os.environ["LOCAL_TTS_ZK_VOICE_ROOT"])
    imported = ZKVoiceImporter().import_directory(voice_root)
    reference_voice = next(voice for voice in imported.voices if voice.voice_id == "zk_vbee_anh_khoi")
    registry = smoke_registry(reference_voice)
    output_dir = Path(__file__).resolve().parents[1] / "outputs" / "phase3_smoke"
    engine = VieNeuEngine(registry, output_dir, precision="fp32")
    engine.start()
    metrics_path = output_dir / "phase3_metrics.json"
    metrics = {"backend": "VieNeu v3 Turbo ONNX/CPU fp32", "startup_seconds": engine.startup_seconds, "results": []}
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        voice_ids = os.getenv("LOCAL_TTS_SMOKE_VOICE_IDS", "vieneu_adam,zk_vbee_anh_khoi").split(",")
        for voice_id in voice_ids:
            result = engine.synthesize("Xin chào.", voice_id)
            metrics["results"].append({
                "voice_id": result.voice_id,
                "generation_seconds": result.generation_seconds,
                "audio_duration_seconds": result.audio_duration_seconds,
                "rtf": result.rtf,
                "sample_rate": result.sample_rate,
                "output_path": str(result.output_path),
            })
            metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        engine.close()
    print(metrics_path)


if __name__ == "__main__":
    main()
