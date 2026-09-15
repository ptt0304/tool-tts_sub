from __future__ import annotations

import sys
import os
import json
import logging
from pathlib import Path

from local_tts.api import create_app
from local_tts.engine import VieNeuEngine
from local_tts.models import Voice, VoiceCategory, VoiceStatus
from local_tts.server import serve
from local_tts.service import TTSService
from local_tts.voice import VoiceRegistry


def application_root() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]


def build_service(root: Path) -> tuple[TTSService, VieNeuEngine]:
    registry_path = root / "voices" / "registry.json"
    records = json.loads(registry_path.read_text(encoding="utf-8")).get("voices", []) if registry_path.exists() else []
    # Built-in presets are runtime-owned. Older registry files may contain Adam
    # after an enable operation; discard that record before adding the canonical
    # preset so a restart can never create a duplicate voice_id.
    records = [record for record in records if record.get("voice_id") != "vieneu_adam"]
    voices = [Voice(voice_id=r["voice_id"], display_name=r["display_name"], status=VoiceStatus(r["status"]), source=r["source"], engine=r["engine"], reference_audio=Path(r["reference_audio"]) if r.get("reference_audio") else None, reference_text=Path(r["reference_text"]) if r.get("reference_text") else None, metadata=r.get("metadata", {}), status_reason=r.get("status_reason")) for r in records]
    voices.insert(0, Voice("vieneu_adam", "Adam", VoiceStatus.READY, "VieNeu built-in preset", "vieneu_v3", category=VoiceCategory.PRESET, metadata={"preset_name": "Adam"}))
    registry = VoiceRegistry(voices)
    engine = VieNeuEngine(registry, root / "outputs")
    return TTSService(registry, engine, registry_path), engine


def run_local_service() -> None:
    root = application_root()
    for name in ("models", "voices", "voices/backups", "config", "logs", "logs/diagnostics", "outputs", "outputs/previews", "outputs/validation"):
        (root / name).mkdir(parents=True, exist_ok=True)
    config_path = root / "config" / "settings.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    cache = Path(config.get("model_cache", "models/huggingface"))
    if not cache.is_absolute():
        cache = root / cache
    os.environ["HF_HOME"] = str(cache)
    logging.basicConfig(level=logging.INFO, handlers=[logging.FileHandler(root / "logs" / "local_tts.log", encoding="utf-8"), logging.StreamHandler()])
    service, engine = build_service(root)
    print("Server: Loading")
    print("Address: 127.0.0.1:8765")
    print("Engine: VieNeu | Backend: ONNX CPU")
    try:
        engine.start()
    except Exception as error:
        print(f"Model: Error ({error})")
        raise
    print("Model: Ready")
    print(f"Voices: {sum(v.status is VoiceStatus.READY for v in service.list_voices())} ready")
    try:
        print("Server: Running | Ctrl+C to exit")
        serve(create_app(service, root / "outputs"), host="127.0.0.1", port=int(config.get("port", 8765)))
    finally:
        engine.close()


def run_local_gui() -> None:
    """Run the browser-based localhost operator UI."""
    root = application_root()
    for name in ("models", "voices", "voices/backups", "config", "logs", "logs/diagnostics", "outputs", "outputs/previews", "outputs/validation"):
        (root / name).mkdir(parents=True, exist_ok=True)
    config_path = root / "config" / "settings.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    cache = Path(config.get("model_cache", "models/huggingface"))
    os.environ["HF_HOME"] = str(cache if cache.is_absolute() else root / cache)
    logging.basicConfig(level=logging.INFO, handlers=[logging.FileHandler(root / "logs" / "local_tts.log", encoding="utf-8"), logging.StreamHandler()])
    service, engine = build_service(root)
    print("Local_TTS UI: Loading model")
    try:
        engine.start()
        port = int(config.get("port", 8765))
        import threading
        import webbrowser
        threading.Timer(0.75, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
        print(f"Local_TTS UI: http://127.0.0.1:{port}/")
        serve(create_app(service, root / "outputs"), host="127.0.0.1", port=port)
    finally:
        engine.close()
