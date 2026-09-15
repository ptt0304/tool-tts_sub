import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from local_tts.desktop import build_service


class DesktopRegistryTests(unittest.TestCase):
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
