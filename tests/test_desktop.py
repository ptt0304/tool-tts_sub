import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from local_tts.desktop import build_service


class DesktopRegistryTests(unittest.TestCase):
    def test_chunking_defaults_are_loaded_from_app_config(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "voices").mkdir()
            (root / "config").mkdir()
            (root / "config" / "settings.json").write_text(
                json.dumps({"tts_chunking": {"hard_max_syllables": 40, "crossfade_ms": 7}}),
                encoding="utf-8",
            )
            service, _ = build_service(root)

        self.assertEqual(service._chunking_settings.hard_max_syllables, 40)
        self.assertEqual(service._chunking_settings.crossfade_ms, 7)

    def test_persisted_builtin_voice_does_not_duplicate_runtime_preset(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "voices").mkdir()
            (root / "voices" / "registry.json").write_text(json.dumps({"voices": [{
                "voice_id": "vieneu_adam",
                "display_name": "Adam",
                "status": "READY",
                "source": "old runtime registry",
                "engine": "vieneu_v3",
            }]}), encoding="utf-8")
            service, _ = build_service(root)
            self.assertEqual([voice.voice_id for voice in service.list_voices()], ["vieneu_adam"])

    def test_packaged_piper_assets_add_fixed_voice(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "voices").mkdir()
            (root / "models" / "piper" / "runtime" / "espeak-ng-data").mkdir(parents=True)
            (root / "models" / "piper" / "runtime" / "piper.exe").write_bytes(b"exe")
            (root / "models" / "piper" / "NgocHuyen.onnx").write_bytes(b"onnx")
            (root / "models" / "piper" / "NgocHuyen.onnx.json").write_text("{}", encoding="utf-8")

            service, _ = build_service(root)

        voice = next(voice for voice in service.list_voices() if voice.voice_id == "piper_ngoc_huyen")
        self.assertEqual(voice.engine, "piper")
        self.assertEqual(voice.category, "FIXED_MODEL")
        self.assertEqual(voice.status, "READY")
        self.assertEqual(voice.as_dict()["category"], "FIXED_MODEL")
