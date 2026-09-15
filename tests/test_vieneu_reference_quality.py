import time
import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from local_tts.engine.vieneu_engine import VieNeuEngine
from local_tts.models import Voice, VoiceStatus
from local_tts.voice import VoiceRegistry


class _FakeBackend:
    def __init__(self):
        self.extract_calls = []
        self.prepare_calls = []

    def extract_speaker_emb(self, path):
        self.extract_calls.append(path)
        return np.array([9.0], dtype=np.float32)

    def prepare_reference(self, path, **kwargs):
        self.prepare_calls.append((path, kwargs))
        return np.array([1.0], dtype=np.float32), np.ones((2, 16), dtype=np.int64)


class _FakeTTS:
    sample_rate = 8_000

    def __init__(self):
        self.engine = _FakeBackend()
        self.infer_calls = []

    def infer(self, text, **kwargs):
        self.infer_calls.append((text, kwargs))
        return np.zeros(800, dtype=np.float32)

    def save(self, audio, path):
        with wave.open(path, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(self.sample_rate)
            output.writeframes(np.zeros(len(audio), dtype="<i2").tobytes())


def _write_wav(path: Path, seconds: float) -> None:
    sample_rate = 8_000
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(b"\0\0" * int(sample_rate * seconds))


class VieNeuReferenceQualityTests(unittest.TestCase):
    def _engine(self, root: Path, seconds: float):
        wav = root / "voice.wav"
        transcript = root / "voice.txt"
        _write_wav(wav, seconds)
        transcript.write_text("Đây là transcript đi kèm.", encoding="utf-8")
        voice = Voice("voice", "Voice", VoiceStatus.READY, "test", "vieneu_v3_reference", wav, transcript)
        engine = VieNeuEngine(VoiceRegistry([voice]), root / "outputs")
        engine._tts = _FakeTTS()
        return engine

    def test_short_reference_uses_complete_audio_and_reference_codes(self):
        with TemporaryDirectory() as directory:
            engine = self._engine(Path(directory), 5.0)
            engine.synthesize("Xin chào", "voice")
            backend = engine._tts.engine
            self.assertEqual(backend.extract_calls, [])
            self.assertAlmostEqual(backend.prepare_calls[0][1]["max_seconds"], 5.001, places=3)
            self.assertTrue(backend.prepare_calls[0][1]["use_ref_codes"])
            self.assertTrue(engine._tts.infer_calls[0][1]["use_ref_codes"])
            self.assertIsNotNone(engine._tts.infer_calls[0][1]["voice"]["codes"])

    def test_long_reference_uses_full_speaker_embedding_and_bounded_codes(self):
        with TemporaryDirectory() as directory:
            engine = self._engine(Path(directory), 20.0)
            engine.synthesize("Xin chào", "voice")
            backend = engine._tts.engine
            self.assertEqual(len(backend.extract_calls), 1)
            self.assertAlmostEqual(
                backend.prepare_calls[0][1]["max_seconds"],
                VieNeuEngine.MAX_REFERENCE_CODE_SECONDS + 0.001,
                places=3,
            )

    def test_changed_transcript_invalidates_enrollment_cache(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            engine = self._engine(root, 5.0)
            engine.synthesize("Một", "voice")
            transcript = root / "voice.txt"
            transcript.write_text("Transcript đã thay đổi và dài hơn.", encoding="utf-8")
            time.sleep(0.001)
            engine.synthesize("Hai", "voice")
            self.assertEqual(len(engine._tts.engine.prepare_calls), 2)


if __name__ == "__main__":
    unittest.main()
