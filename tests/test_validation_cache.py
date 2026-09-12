import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import wave
from local_tts.models import Voice, VoiceStatus
from local_tts.voice import VoiceLibraryValidator

class CacheTests(unittest.TestCase):
    def test_ready_cache_retained_and_changed_file_invalidates_it(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            audio, text = root / "ref.wav", root / "ref.txt"
            with wave.open(str(audio), "wb") as stream:
                stream.setparams((1, 2, 16000, 0, "NONE", "none"))
                stream.writeframes(b"\x01\x00" * 1600)
            text.write_text("Xin chào", encoding="utf-8")
            voice = Voice("fixed_id", "Label", VoiceStatus.DISABLED, "test", "vieneu_v3_reference", audio, text)
            validator = VoiceLibraryValidator()
            path = root / "registry.json"
            validator.validate_incremental([voice], path)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["voices"][0]["status"] = "READY"
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(validator.validate_incremental([voice], path)[0].status, VoiceStatus.READY)
            text.write_text("Changed reference transcript", encoding="utf-8")
            self.assertEqual(validator.validate_incremental([voice], path)[0].status, VoiceStatus.DISABLED)
