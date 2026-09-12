import unittest

from local_tts.engine import MockTTSEngine
from local_tts.models import Voice, VoiceStatus
from local_tts.service import TTSService, VoiceNotReadyError
from local_tts.voice import VoiceRegistry


class TTSServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ready = Voice("mock_ready", "Display can change", VoiceStatus.READY, "test", "mock")
        self.unsupported = Voice("fixed_model", "Fixed", VoiceStatus.UNSUPPORTED, "test", "mock")
        self.invalid = Voice("broken_pair", "Broken", VoiceStatus.INVALID, "test", "mock")
        self.engine = MockTTSEngine(["mock_ready"])
        self.service = TTSService(VoiceRegistry([self.ready, self.unsupported, self.invalid]), self.engine)

    def test_service_uses_mock_engine_and_voice_id(self) -> None:
        result = self.service.synthesize("Xin chào", "mock_ready", speed=1.2)
        self.assertEqual(result.voice_id, "mock_ready")
        self.assertEqual(self.engine.calls, [("Xin chào", "mock_ready", 1.2)])
        self.assertEqual(self.service.health().status, "READY")
        self.assertEqual(self.service.list_voices()[0].voice_id, "broken_pair")

    def test_unsupported_and_invalid_voices_are_not_sent_to_engine(self) -> None:
        for voice_id in ("fixed_model", "broken_pair"):
            with self.assertRaises(VoiceNotReadyError):
                self.service.synthesize("Xin chào", voice_id)
        self.assertEqual(self.engine.calls, [])

    def test_reference_voice_becomes_ready_only_after_validation_synthesis(self) -> None:
        reference = Voice("reference", "Reference", VoiceStatus.DISABLED, "test", "mock")
        engine = MockTTSEngine(["reference"])
        service = TTSService(VoiceRegistry([reference]), engine)
        service.enable_reference_voice("reference")
        self.assertEqual(service.registry.get("reference").status, VoiceStatus.READY)
        self.assertEqual(engine.calls[0][1], "reference")
