from __future__ import annotations

import argparse
import os
from pathlib import Path

from local_tts.voice import VoiceLibraryValidator, ZKVoiceImporter
from local_tts.models import VoiceStatus


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", default="gui", choices=["validate-voices", "serve", "gui"])
    parser.add_argument("--voice-root")
    parser.add_argument("--zk-voice-root", default=os.getenv("LOCAL_TTS_ZK_VOICE_ROOT"))
    parser.add_argument("--xa-voice-root", default=os.getenv("LOCAL_TTS_XA_VOICE_ROOT"))
    parser.add_argument("--registry", default="voices/registry.json")
    parser.add_argument("--infer", action="store_true")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--paired-only", action="store_true", help="exclude incomplete WAV/TXT assets from the registry")
    args = parser.parse_args()
    if args.command == "serve":
        from local_tts.desktop import run_local_service
        run_local_service()
        return
    if args.command == "gui":
        from local_tts.desktop import run_local_gui
        run_local_gui()
        return
    roots = []
    zk_root = args.voice_root or args.zk_voice_root
    if zk_root:
        roots.append((ZKVoiceImporter(display_prefix="zk_"), Path(zk_root)))
    if args.xa_voice_root:
        xa_root = Path(args.xa_voice_root)
        vietnamese_root = xa_root / "Việt Nam"
        english_root = xa_root / "English"
        roots.append((ZKVoiceImporter(
            id_prefix="xa",
            source="Xuân An Voices mẫu/Việt Nam",
            display_prefix="xa_",
            importer_name="xuan_an_voice_directory",
        ), vietnamese_root if vietnamese_root.is_dir() else xa_root))
        if english_root.is_dir():
            roots.append((ZKVoiceImporter(
                id_prefix="xa_en",
                source="Xuân An Voices mẫu/English",
                display_prefix="xa_en_",
                importer_name="xuan_an_english_voice_directory",
            ), english_root))
    if not roots:
        parser.error("--voice-root, --zk-voice-root, or --xa-voice-root is required")
    imported_results = [importer.import_directory(root) for importer, root in roots]
    issues = [issue for result in imported_results for issue in result.issues]
    imported_voices = [voice for result in imported_results for voice in result.voices]
    if args.paired_only:
        imported_voices = [
            voice for voice in imported_voices
            if voice.reference_audio is not None and voice.reference_text is not None
        ]
    if issues and not imported_voices:
        parser.error(str(issues))
    if len({voice.voice_id for voice in imported_voices}) != len(imported_voices):
        parser.error("voice_id collision across imported libraries")
    voices = VoiceLibraryValidator().validate_incremental(imported_voices, Path(args.registry), args.infer, max(0, args.limit))
    counts = {status.value: sum(voice.status.value == status.value for voice in voices) for status in VoiceStatus}
    print({"total": len(voices), "counts": counts, "issues": [issue.code for issue in issues]})


if __name__ == "__main__":
    main()
