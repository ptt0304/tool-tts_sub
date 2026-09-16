import io
import unittest
import wave
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from local_tts.audio import ChunkingSettings, PauseSettings, estimate_syllables, normalize_text, plan_text_chunks, synthesize_with_pauses
from local_tts.audio.pauses import _normalize_chunk_edges
from local_tts.engine import MockTTSEngine


class PauseSynthesisTests(unittest.TestCase):
    def test_punctuation_and_break_insert_exact_silence(self):
        engine = MockTTSEngine(["voice"])
        settings = PauseSettings(comma=0.10, period=0.20, break_time=0.30)
        result = synthesize_with_pauses(
            lambda text: engine.synthesize(text, "voice"),
            "Xin chào, bạn.[break] Cảm ơn",
            settings,
        )
        self.assertEqual([call[0] for call in engine.calls], ["Xin chào, bạn.", "Cảm ơn"])
        with wave.open(io.BytesIO(result.wav_bytes), "rb") as reader:
            self.assertEqual(reader.getframerate(), 48_000)
            self.assertAlmostEqual(reader.getnframes() / reader.getframerate(), 0.40, places=2)

    def test_consecutive_pause_markers_use_longest_pause(self):
        engine = MockTTSEngine(["voice"])
        result = synthesize_with_pauses(
            lambda text: engine.synthesize(text, "voice"),
            "Một câu.\nCâu hai",
            PauseSettings(period=0.20, newline=0.40),
        )
        self.assertEqual(len(engine.calls), 2)
        self.assertAlmostEqual(result.audio_duration_seconds, 0.50, places=2)

    def test_spaces_are_collapsed_and_do_not_override_period(self):
        engine = MockTTSEngine(["voice"])
        result = synthesize_with_pauses(
            lambda text: engine.synthesize(text, "voice"),
            "a  b.   c",
            PauseSettings(space=0.10, period=0.25),
        )
        self.assertEqual([call[0] for call in engine.calls], ["a b.", "c"])
        # Whitespace no longer creates an isolated TTS request.
        self.assertAlmostEqual(result.audio_duration_seconds, 0.35, places=2)

    def test_zero_space_keeps_natural_phrase_and_collapses_whitespace(self):
        engine = MockTTSEngine(["voice"])
        synthesize_with_pauses(
            lambda text: engine.synthesize(text, "voice"),
            "a   b",
            PauseSettings(space=0),
        )
        self.assertEqual([call[0] for call in engine.calls], ["a b"])

    def test_question_ellipsis_and_ignored_marks(self):
        engine = MockTTSEngine(["voice"])
        result = synthesize_with_pauses(
            lambda text: engine.synthesize(text, "voice"),
            "'Bạn' ổn không? \"Tôi\" ổn!... Tiếp tục",
            PauseSettings(question=0.20, ellipsis=0.30),
        )
        self.assertEqual(
            [call[0] for call in engine.calls],
            ["'Bạn' ổn không?", '"Tôi" ổn!...', "Tiếp tục"],
        )
        # Emotional punctuation and quotes are preserved for model prosody.
        self.assertAlmostEqual(result.audio_duration_seconds, 0.65, places=2)

    def test_invalid_pause_value_is_rejected(self):
        with self.assertRaises(ValueError):
            PauseSettings(comma=-0.1)

    def test_model_edge_silence_is_trimmed_before_configured_pause(self):
        sample_rate = 8_000
        leading_frames = round(0.20 * sample_rate)
        active_frames = round(0.10 * sample_rate)
        trailing_frames = round(0.30 * sample_rate)
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(sample_rate)
            writer.writeframes(
                (b"\x00\x00" * leading_frames)
                + (int(8_000).to_bytes(2, "little", signed=True) * active_frames)
                + (b"\x00\x00" * trailing_frames)
            )
        with wave.open(io.BytesIO(wav_buffer.getvalue()), "rb") as reader:
            params = reader.getparams()
            normalized, trimmed_leading, trimmed_trailing = _normalize_chunk_edges(
                reader.readframes(reader.getnframes()), params
            )

        # Keep a small 12 ms safety margin on both sides of voiced content,
        # but remove the model's much longer generated silence.
        self.assertAlmostEqual(trimmed_leading, 0.188, places=3)
        self.assertAlmostEqual(trimmed_trailing, 0.288, places=3)
        self.assertAlmostEqual(len(normalized) / 2 / sample_rate, 0.124, places=3)

    def test_long_text_uses_syllable_soft_constraints_not_character_chunks(self):
        engine = MockTTSEngine(["voice"])
        text = " ".join(["tiếng"] * 100)
        synthesize_with_pauses(
            lambda chunk: engine.synthesize(chunk, "voice"),
            text,
            PauseSettings(),
        )
        chunks = [call[0] for call in engine.calls]
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(estimate_syllables(chunk) <= 32 for chunk in chunks))
        self.assertEqual(" ".join(chunks), text)

    def test_zero_pause_semantic_chunks_use_tiny_crossfade(self):
        engine = MockTTSEngine(["voice"])
        text = " ".join(["tiếng"] * 20)
        result = synthesize_with_pauses(
            lambda chunk: engine.synthesize(chunk, "voice"),
            text,
            PauseSettings(space=0),
            ChunkingSettings(preferred_syllables=6, soft_max_syllables=8, hard_max_syllables=10, crossfade_ms=10),
        )
        raw_duration = len(engine.calls) * 0.05
        self.assertGreater(len(engine.calls), 1)
        self.assertLess(result.audio_duration_seconds, raw_duration)

    def test_complete_sentence_is_not_split_at_comma(self):
        chunks = plan_text_chunks("Xin chào, hôm nay bạn khỏe không?")
        self.assertEqual([chunk.text for chunk in chunks], ["Xin chào, hôm nay bạn khỏe không?"])

    def test_long_sentence_prefers_semantic_boundary(self):
        text = (
            "Mặc dù trời đã tối, nhưng cô ấy vẫn đứng trước cửa, chờ người mà cô đã không "
            "gặp suốt mười năm và vẫn không muốn rời khỏi nơi ấy một mình."
        )
        chunks = plan_text_chunks(text, ChunkingSettings(hard_max_syllables=24))
        self.assertGreater(len(chunks), 1)
        self.assertIn(chunks[0].reason, {"comma", "strong_clause", "conjunction", "phrase"})
        self.assertEqual(" ".join(chunk.text for chunk in chunks), text)

    def test_vietnamese_protected_phrases_and_emotion_normalization(self):
        self.assertEqual(len(plan_text_chunks("Anh ấy đã đi rồi.")), 1)
        self.assertEqual(len(plan_text_chunks("Tôi mua hai chiếc xe mới.")), 1)
        self.assertEqual(normalize_text("Trời ơi!!! Anh làm gì vậy??"), "Trời ơi! Anh làm gì vậy?")

    def test_abbreviation_and_closing_quote_do_not_confuse_sentences(self):
        chunks = plan_text_chunks('TS. An nói: "Tôi đồng ý." Sau đó ông rời đi.')
        self.assertEqual(
            [chunk.text for chunk in chunks],
            ['TS. An nói: "Tôi đồng ý."', "Sau đó ông rời đi."],
        )

    def test_successful_join_removes_engine_chunk_files(self):
        engine = MockTTSEngine(["voice"])
        tmp = Path(".tmp-tests") / f"pause-{uuid4().hex}"
        tmp.mkdir(parents=True)
        try:
            created: list[Path] = []

            def synthesize(text: str):
                result = engine.synthesize(text, "voice")
                path = tmp / f"chunk_{len(created)}.wav"
                path.write_bytes(result.wav_bytes)
                created.append(path)
                return replace(result, output_path=path)

            result = synthesize_with_pauses(
                synthesize,
                "Đoạn một. Đoạn hai.",
                PauseSettings(),
            )
            self.assertGreater(len(result.wav_bytes), 44)
            self.assertTrue(created)
            self.assertTrue(all(not path.exists() for path in created))
        finally:
            tmp.rmdir()

    def test_empty_audio_chunk_is_bisected_and_retried(self):
        engine = MockTTSEngine(["voice"])
        attempted: list[str] = []

        def synthesize(text: str):
            attempted.append(text)
            if len(text) > 90:
                raise RuntimeError("VieNeu returned empty audio")
            return engine.synthesize(text, "voice")

        text = " ".join(["tiếng"] * 60)
        result = synthesize_with_pauses(synthesize, text, PauseSettings())
        self.assertGreater(len(result.wav_bytes), 44)
        self.assertTrue(any(len(chunk) > 90 for chunk in attempted))
        self.assertTrue(engine.calls)
        self.assertTrue(all(len(call[0]) <= 90 for call in engine.calls))
        self.assertEqual(" ".join(call[0] for call in engine.calls), text)
