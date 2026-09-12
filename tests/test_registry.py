from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from local_tts.models import VoiceStatus
from local_tts.voice import VoiceRegistry, ZKVoiceImporter


class ZKVoiceImporterTests(unittest.TestCase):
    def test_pairs_and_missing_files_are_reported_as_distinct_statuses(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "vbee_Anh Khôi.wav").write_bytes(b"wav")
            (root / "vbee_Anh Khôi.txt").write_text("text", encoding="utf-8")
            (root / "only_wav.wav").write_bytes(b"wav")
            (root / "only_text.txt").write_text("text", encoding="utf-8")

            result = ZKVoiceImporter().import_directory(root)

        statuses = {voice.voice_id: voice.status for voice in result.voices}
        self.assertEqual(statuses["zk_vbee_anh_khoi"], VoiceStatus.REQUIRES_REFERENCE)
        self.assertEqual(statuses["zk_only_wav"], VoiceStatus.INVALID)
        self.assertEqual(statuses["zk_only_text"], VoiceStatus.INVALID)

    def test_stable_id_does_not_depend_on_display_name_at_runtime(self) -> None:
        self.assertEqual(ZKVoiceImporter.stable_slug("vbee_Anh Khôi"), "vbee_anh_khoi")
        self.assertEqual(ZKVoiceImporter.stable_slug("ZK_Nữ Long Tiếng"), "zk_nu_long_tieng")

    def test_duplicate_normalized_id_gets_deterministic_suffixes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("vbee_Anh Khoi", "vbee_Anh Khôi"):
                (root / f"{name}.wav").write_bytes(b"wav")
                (root / f"{name}.txt").write_text("text", encoding="utf-8")

            result = ZKVoiceImporter().import_directory(root)

        self.assertEqual(len(result.voices), 2)
        self.assertEqual(len({voice.voice_id for voice in result.voices}), 2)
        self.assertTrue(all(voice.voice_id.startswith("zk_vbee_anh_khoi_") for voice in result.voices))
        self.assertEqual([issue.code for issue in result.issues], ["duplicate_normalized_id"])

    def test_invalid_directory_is_reported(self) -> None:
        result = ZKVoiceImporter().import_directory(Path("does-not-exist"))
        self.assertEqual(result.voices, [])
        self.assertEqual(result.issues[0].code, "invalid_path")

    def test_registry_lookup_uses_stable_id(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "vbee_Anh Khôi.wav").write_bytes(b"wav")
            (root / "vbee_Anh Khôi.txt").write_text("text", encoding="utf-8")
            registry, _ = VoiceRegistry.from_zk_directory(root)

        self.assertEqual(registry.get("zk_vbee_anh_khoi").display_name, "vbee_Anh Khôi")
        self.assertIsNone(registry.get("vbee_Anh Khôi"))
