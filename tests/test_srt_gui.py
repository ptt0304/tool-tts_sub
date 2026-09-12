from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from local_tts.engine import MockTTSEngine
from local_tts.gui import generate_srt_audio, parse_srt
from local_tts.models import Voice, VoiceStatus
from local_tts.service import TTSService
from local_tts.voice import VoiceRegistry


class SRTGuiSupportTests(unittest.TestCase):
    def test_parser_preserves_cues_and_skips_invalid_blocks(self):
        cues = parse_srt("1\n00:00:01,000 --> 00:00:02,500\nXin chào\n\ninvalid\n\n2\n00:00:03,000 --> 00:00:04,000\nTạm biệt")
        self.assertEqual([(cue.index, cue.start, cue.text) for cue in cues], [(1, "00:00:01,000", "Xin chào"), (2, "00:00:03,000", "Tạm biệt")])

    def test_export_generates_one_deterministic_file_per_cue(self):
        cues = parse_srt("7\n00:00:00,000 --> 00:00:01,000\nXin chào\n\n8\n00:00:01,000 --> 00:00:02,000\nTạm biệt")
        service = TTSService(VoiceRegistry([Voice("voice", "Voice", VoiceStatus.READY, "test", "mock")]), MockTTSEngine(["voice"]))
        progress = []
        with TemporaryDirectory() as directory:
            outputs = generate_srt_audio(service, cues, "voice", Path(directory), progress=lambda done, total, cue: progress.append((done, total, cue.index)))
            self.assertEqual([path.name for path in outputs], ["srt_000007.wav", "srt_000008.wav"])
            self.assertTrue(all(path.is_file() for path in outputs))
        self.assertEqual(progress, [(1, 2, 7), (2, 2, 8)])
