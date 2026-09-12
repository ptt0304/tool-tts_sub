from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from local_tts.api import create_app
from local_tts.engine import MockTTSEngine
from local_tts.models import Voice, VoiceStatus
from local_tts.service import TTSService
from local_tts.voice import VoiceRegistry


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        ready = Voice("mock_voice", "Mock", VoiceStatus.READY, "test", "mock")
        pending = Voice("pending_voice", "Pending", VoiceStatus.REQUIRES_REFERENCE, "test", "mock")
        self.tmp = TemporaryDirectory()
        self.client = TestClient(create_app(TTSService(VoiceRegistry([ready, pending]), MockTTSEngine(["mock_voice"])), Path(self.tmp.name)))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def payload(self, **overrides):
        return {"segment_id": "000123", "speaker_id": "SPK_02", "voice_id": "mock_voice", "text": "Xin chào", "speed": 1.0} | overrides

    def test_health_voices_lookup_generate_and_batch(self) -> None:
        self.assertIn("Local_TTS", self.client.get("/").text)
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/voices").status_code, 200)
        self.assertEqual(self.client.get("/api/voices/mock_voice").status_code, 200)
        generated = self.client.post("/api/tts/generate", json=self.payload())
        self.assertEqual(generated.status_code, 200)
        self.assertTrue(Path(generated.json()["audio_path"]).is_file())
        batch = self.client.post("/api/tts/batch", json={"items": [self.payload(segment_id="a"), self.payload(segment_id="b")]})
        self.assertEqual([item["segment_id"] for item in batch.json()["items"]], ["a", "b"])

    def test_invalid_unknown_and_unsafe_requests(self) -> None:
        self.assertEqual(self.client.post("/api/tts/generate", json=self.payload(text="   ")).json()["error"]["code"], "INVALID_TEXT")
        self.assertEqual(self.client.post("/api/tts/generate", json=self.payload(voice_id="missing")).json()["error"]["code"], "VOICE_NOT_FOUND")
        self.assertEqual(self.client.post("/api/tts/generate", json=self.payload(segment_id="../bad")).json()["error"]["code"], "INVALID_TEXT")

    def test_batch_keeps_failed_segments_and_continues(self):
        response = self.client.post("/api/tts/batch", json={"items": [self.payload(segment_id="bad", voice_id="missing"), self.payload(segment_id="good")]})
        rows = response.json()["items"]
        self.assertEqual([row["segment_id"] for row in rows], ["bad", "good"])
        self.assertEqual(rows[0]["error"]["code"], "VOICE_NOT_FOUND")
        self.assertTrue(Path(rows[1]["audio_path"]).is_file())

    def test_windows_devices_and_empty_text_are_rejected(self):
        for name in ("CON", "NUL", "COM1", "LPT9", "C:\\bad", "/bad"):
            self.assertEqual(self.client.post("/api/tts/generate", json=self.payload(segment_id=name)).status_code, 422)
        self.assertEqual(self.client.post("/api/tts/generate", json=self.payload(text="")).json()["error"]["code"], "INVALID_TEXT")

    def test_enable_rejects_non_reference_pending_voice(self):
        response = self.client.post("/api/voices/pending_voice/enable")
        self.assertEqual(response.status_code, 409)
