from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import wave
import json

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

    def test_registry_stores_application_local_assets_as_relative_paths(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            asset_dir = root / "ZK_Voices"
            asset_dir.mkdir()
            audio, text = asset_dir / "voice.wav", asset_dir / "voice.txt"
            audio.write_bytes(b"wav")
            text.write_text("text", encoding="utf-8")
            registry = root / "voices" / "registry.json"
            voice = Voice("zk_voice", "Voice", VoiceStatus.READY, "test", "vieneu_v3_reference", audio, text)

            VoiceLibraryValidator.save(registry, [voice])
            record = json.loads(registry.read_text(encoding="utf-8"))["voices"][0]

        self.assertEqual(record["reference_audio"], str(Path("ZK_Voices") / "voice.wav"))
        self.assertEqual(record["reference_text"], str(Path("ZK_Voices") / "voice.txt"))
