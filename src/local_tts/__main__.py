from __future__ import annotations

import argparse
import os
from pathlib import Path

from local_tts.voice import VoiceLibraryValidator, ZKVoiceImporter
from local_tts.models import VoiceStatus


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", default="gui", choices=["validate-voices", "serve", "gui"])
    parser.add_argument("--voice-root", default=os.getenv("LOCAL_TTS_ZK_VOICE_ROOT"))
    parser.add_argument("--registry", default="voices/registry.json")
    parser.add_argument("--infer", action="store_true")
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()
    if args.command == "serve":
        from local_tts.desktop import run_local_service
        run_local_service()
        return
    if args.command == "gui":
        from local_tts.desktop import run_local_gui
        run_local_gui()
        return
    if not args.voice_root:
        parser.error("--voice-root or LOCAL_TTS_ZK_VOICE_ROOT is required")
    imported = ZKVoiceImporter().import_directory(Path(args.voice_root))
    if imported.issues and not imported.voices:
        parser.error(str(imported.issues))
    voices = VoiceLibraryValidator().validate_incremental(imported.voices, Path(args.registry), args.infer, max(0, args.limit))
    counts = {status.value: sum(voice.status.value == status.value for voice in voices) for status in VoiceStatus}
    print({"total": len(voices), "counts": counts, "issues": [issue.code for issue in imported.issues]})


if __name__ == "__main__":
    main()
