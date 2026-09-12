from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuration only. Phase 2 does not create an HTTP server or model."""

    zk_voice_root: Path | None = None

    @classmethod
    def from_environment(cls) -> "Settings":
        raw_path = os.getenv("LOCAL_TTS_ZK_VOICE_ROOT")
        return cls(zk_voice_root=Path(raw_path).expanduser() if raw_path else None)
