from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import wave

from local_tts.models import Voice, VoiceStatus
from local_tts.voice import VoiceLibraryValidator


class ValidatorTests(unittest.TestCase):
    def test_valid_wav_is_disabled_until_inference(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); wav = root / "voice.wav"; text = root / "voice.txt"
            with wave.open(str(wav), "wb") as out:
                out.setnchannels(1); out.setsampwidth(2); out.setframerate(16000); out.writeframes(b"\0\0" * 160)
            text.write_text("xin chào", encoding="utf-8")
            voice = Voice("zk_test", "Test", VoiceStatus.REQUIRES_REFERENCE, "test", "vieneu_v3_reference", wav, text)
            validated = VoiceLibraryValidator().validate_files([voice])[0]
        self.assertEqual(validated.status, VoiceStatus.DISABLED)
        self.assertEqual(validated.metadata["reference_duration_seconds"], "0.010")
