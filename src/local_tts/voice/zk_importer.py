from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from local_tts.models import Voice, VoiceCategory, VoiceStatus


@dataclass(frozen=True, slots=True)
class ImportIssue:
    code: str
    path: Path
    detail: str


@dataclass(frozen=True, slots=True)
class VoiceImportResult:
    voices: list[Voice]
    issues: list[ImportIssue]


class ZKVoiceImporter:
    """Imports one configured, flat OVoice_Voices directory without copying media."""

    def __init__(
        self,
        *,
        id_prefix: str = "zk",
        source: str = "ZK OVoice_Voices",
        display_prefix: str = "",
        importer_name: str = "zk_voice_directory",
    ) -> None:
        normalized_prefix = self.stable_slug(id_prefix)
        if not normalized_prefix:
            raise ValueError("id_prefix must contain at least one letter or digit")
        self._id_prefix = normalized_prefix
        self._source = source
        self._display_prefix = display_prefix
        self._importer_name = importer_name

    def import_directory(self, root: Path) -> VoiceImportResult:
        if not root.exists() or not root.is_dir():
            return VoiceImportResult([], [ImportIssue("invalid_path", root, "voice directory does not exist or is not a directory")])
        try:
            files = sorted((path for path in root.iterdir() if path.is_file()), key=lambda path: path.name.casefold())
        except OSError as error:
            return VoiceImportResult([], [ImportIssue("invalid_path", root, str(error))])

        wavs = {path.stem.casefold(): path for path in files if path.suffix.casefold() == ".wav"}
        texts = {path.stem.casefold(): path for path in files if path.suffix.casefold() == ".txt"}
        candidates: list[tuple[str, Path | None, Path | None, VoiceStatus, str | None]] = []
        for stem in sorted(set(wavs) | set(texts)):
            wav, text = wavs.get(stem), texts.get(stem)
            name = (wav or text).stem
            if wav and text:
                candidates.append((name, wav, text, VoiceStatus.REQUIRES_REFERENCE, "unverified_reference"))
            elif wav:
                candidates.append((name, wav, None, VoiceStatus.INVALID, "missing_reference_text"))
            else:
                candidates.append((name, None, text, VoiceStatus.INVALID, "missing_reference_audio"))

        issues: list[ImportIssue] = []
        groups: dict[str, list[tuple[str, Path | None, Path | None, VoiceStatus, str | None]]] = {}
        for candidate in candidates:
            slug = self.stable_slug(candidate[0])
            normalized_id = f"{self._id_prefix}_{slug}"
            if not slug:
                issues.append(ImportIssue("invalid_name", candidate[1] or candidate[2], "name cannot form a stable voice_id"))
                continue
            groups.setdefault(normalized_id, []).append(candidate)

        voices: list[Voice] = []
        for normalized_id, grouped in sorted(groups.items()):
            collision = len(grouped) > 1
            if collision:
                issues.append(ImportIssue("duplicate_normalized_id", root, normalized_id))
            for name, wav, text, status, reason in grouped:
                voice_id = normalized_id
                if collision:
                    voice_id = f"{normalized_id}_{hashlib.sha256(name.encode('utf-8')).hexdigest()[:8]}"
                voices.append(Voice(
                    voice_id=voice_id,
                    display_name=f"{self._display_prefix}{name}",
                    source=self._source,
                    engine="vieneu_v3_reference",
                    status=status,
                    reference_audio=wav,
                    reference_text=text,
                    metadata={"importer": self._importer_name, "library_prefix": self._id_prefix},
                    category=VoiceCategory.REFERENCE,
                    status_reason=reason,
                ))
        return VoiceImportResult(sorted(voices, key=lambda voice: voice.voice_id), issues)

    @staticmethod
    def stable_slug(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value).replace("đ", "d").replace("Đ", "D")
        ascii_value = "".join(char for char in normalized if not unicodedata.combining(char)).lower()
        return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", ascii_value)).strip("_")
