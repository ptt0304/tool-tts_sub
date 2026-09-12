"""Model-heavy integration test. Opt in with LOCAL_TTS_RUN_VIENEU_SMOKE=1."""

import os
from pathlib import Path
import unittest

from local_tts.engine.vieneu_engine import VieNeuEngine, smoke_registry
from local_tts.voice import ZKVoiceImporter


@unittest.skipUnless(os.getenv("LOCAL_TTS_RUN_VIENEU_SMOKE") == "1", "set LOCAL_TTS_RUN_VIENEU_SMOKE=1")
class VieNeuSmokeTests(unittest.TestCase):
    def test_preset_and_zk_reference_generate_wav(self) -> None:
        root = Path(os.environ["LOCAL_TTS_ZK_VOICE_ROOT"])
        imported = ZKVoiceImporter().import_directory(root)
        reference = next(voice for voice in imported.voices if voice.voice_id == "zk_vbee_anh_khoi")
        registry = smoke_registry(reference)
        engine = VieNeuEngine(registry, Path("outputs"))
        engine.start()
        try:
            for voice_id in ("vieneu_adam", "zk_vbee_anh_khoi"):
                result = engine.synthesize("Xin chào, đây là kiểm tra giọng nói tiếng Việt.", voice_id)
                self.assertTrue(result.output_path.is_file())
                self.assertEqual(result.sample_rate, 48_000)
                self.assertGreater(result.audio_duration_seconds, 0)
        finally:
            engine.close()
