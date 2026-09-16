from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import io
import wave

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
        self.engine = MockTTSEngine(["mock_voice"])
        self.client = TestClient(create_app(TTSService(VoiceRegistry([ready, pending]), self.engine), Path(self.tmp.name)))

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

    def test_failed_batch_discards_successful_segment_audio(self):
        response = self.client.post("/api/tts/batch", json={"items": [self.payload(segment_id="bad", voice_id="missing"), self.payload(segment_id="good")]})
        rows = response.json()["items"]
        self.assertEqual(response.status_code, 422)
        self.assertEqual([row["segment_id"] for row in rows], ["bad", "good"])
        self.assertEqual(rows[0]["error"]["code"], "VOICE_NOT_FOUND")
        self.assertNotIn("audio_path", rows[1])
        self.assertEqual(list(Path(self.tmp.name).glob("*.wav")), [])

    def test_batch_writes_only_the_combined_wav(self):
        response = self.client.post("/api/tts/batch", json={
            "output_name": "episode_01.txt",
            "items": [self.payload(segment_id="a"), self.payload(segment_id="b")],
        })
        self.assertEqual(response.status_code, 200)
        output = Path(response.json()["output_path"])
        self.assertEqual(output.name, "episode_01.wav")
        self.assertEqual(list(Path(self.tmp.name).glob("*.wav")), [output])

    def test_windows_devices_and_empty_text_are_rejected(self):
        for name in ("CON", "NUL", "COM1", "LPT9", "C:\\bad", "/bad"):
            self.assertEqual(self.client.post("/api/tts/generate", json=self.payload(segment_id=name)).status_code, 422)
        self.assertEqual(self.client.post("/api/tts/generate", json=self.payload(text="")).json()["error"]["code"], "INVALID_TEXT")

    def test_enable_rejects_non_reference_pending_voice(self):
        response = self.client.post("/api/voices/pending_voice/enable")
        self.assertEqual(response.status_code, 409)

    def test_voice_preview_is_exactly_ten_seconds_and_cached(self):
        first = self.client.post("/api/voices/mock_voice/preview")
        second = self.client.post("/api/voices/mock_voice/preview")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.headers["content-type"], "audio/wav")
        self.assertEqual(first.headers["x-preview-seconds"], "10.0")
        with wave.open(io.BytesIO(first.content), "rb") as reader:
            self.assertEqual(reader.getnframes(), reader.getframerate() * 10)
        self.assertEqual(first.content, second.content)
        self.assertEqual(len(self.engine.calls), 1)
        self.assertEqual(len(list((Path(self.tmp.name) / "previews").glob("mock_voice_*.wav"))), 1)

    def test_voice_preview_rejects_non_ready_voice(self):
        response = self.client.post("/api/voices/pending_voice/preview")
        self.assertEqual(response.status_code, 409)

    def test_generate_accepts_pause_configuration(self):
        response = self.client.post("/api/tts/generate", json=self.payload(
            text="Xin chào, bạn khỏe không?",
            pause_settings={"space": 0.0, "comma": 0.1, "period": 0.2, "question": 0.25, "colon": 0.1, "ellipsis": 0.2, "newline": 0.3, "break_time": 0.4},
            chunking_settings={"preferred_syllables": 16, "soft_max_syllables": 24, "hard_max_syllables": 32, "minimum_chunk_syllables": 3, "merge_short_sentences": False},
        ))
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["duration"], 0.3)
        self.assertEqual(len(self.engine.calls), 1)

    def test_invalid_pause_configuration_is_rejected(self):
        response = self.client.post("/api/tts/generate", json=self.payload(
            pause_settings={"comma": -1},
        ))
        self.assertEqual(response.status_code, 422)

        response = self.client.post("/api/tts/generate", json=self.payload(
            chunking_settings={"preferred_syllables": 24, "soft_max_syllables": 16, "hard_max_syllables": 32},
        ))
        self.assertEqual(response.status_code, 422)
