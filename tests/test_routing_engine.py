from pathlib import Path
import unittest

from local_tts.engine import EngineHealth, RoutingEngine, TTSEngine
from local_tts.models import SynthesisResult, Voice, VoiceCategory, VoiceStatus
from local_tts.voice import VoiceRegistry


class RecordingEngine(TTSEngine):
    def __init__(self, voices):
        self.voices = voices
        self.calls = []

    def health(self):
        return EngineHealth("READY", "test")

    def list_voices(self):
        return self.voices

    def synthesize(self, text, voice_id, speed=1.0):
        self.calls.append((text, voice_id, speed))
        return SynthesisResult(b"wav", 22050, voice_id, Path("test.wav"))


class RoutingEngineTests(unittest.TestCase):
    def test_routes_fixed_voice_to_piper(self):
        voice = Voice(
            "piper_test", "Piper", VoiceStatus.READY, "test", "piper",
            category=VoiceCategory.FIXED_MODEL,
        )
        vieneu = RecordingEngine([])
        piper = RecordingEngine([voice.voice_id])
        engine = RoutingEngine(VoiceRegistry([voice]), vieneu, piper)

        result = engine.synthesize("Xin chào", voice.voice_id, 1.25)

        self.assertEqual(result.voice_id, voice.voice_id)
        self.assertEqual(piper.calls, [("Xin chào", voice.voice_id, 1.25)])
        self.assertEqual(vieneu.calls, [])


if __name__ == "__main__":
    unittest.main()
