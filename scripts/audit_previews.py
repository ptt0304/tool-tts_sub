"""Audit every READY voice through the same HTTP preview endpoint as the UI."""

from __future__ import annotations

import io
import json
import urllib.parse
import urllib.request
import wave
from datetime import UTC, datetime
from pathlib import Path


BASE_URL = "http://127.0.0.1:8765"


def main() -> int:
    with urllib.request.urlopen(f"{BASE_URL}/api/voices", timeout=10) as response:
        voices = json.load(response)["voices"]
    results = []
    ready = [voice for voice in voices if voice["status"] == "READY"]
    for index, voice in enumerate(ready, start=1):
        voice_id = voice["voice_id"]
        row = {"voice_id": voice_id, "display_name": voice["display_name"], "ok": False}
        try:
            request = urllib.request.Request(
                f"{BASE_URL}/api/voices/{urllib.parse.quote(voice_id, safe='')}/preview",
                data=b"",
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=180) as response:
                audio = response.read()
                row["http_status"] = response.status
                row["content_type"] = response.headers.get_content_type()
                row["preview_header"] = response.headers.get("X-Preview-Seconds")
            with wave.open(io.BytesIO(audio), "rb") as wav:
                row.update({
                    "channels": wav.getnchannels(),
                    "sample_width": wav.getsampwidth(),
                    "sample_rate": wav.getframerate(),
                    "frames": wav.getnframes(),
                    "duration": wav.getnframes() / wav.getframerate(),
                })
            row["ok"] = (
                row["http_status"] == 200
                and row["content_type"] == "audio/wav"
                and abs(row["duration"] - 10.0) < 0.001
                and row["frames"] > 0
            )
        except Exception as error:
            row["error"] = f"{type(error).__name__}: {error}"
        results.append(row)
        print(f"[{index}/{len(ready)}] {'OK' if row['ok'] else 'FAIL'} {voice_id}", flush=True)

    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "base_url": BASE_URL,
        "total_ready": len(ready),
        "passed": sum(row["ok"] for row in results),
        "failed": sum(not row["ok"] for row in results),
        "results": results,
    }
    output = Path(__file__).resolve().parents[1] / "logs" / "diagnostics" / "preview_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("total_ready", "passed", "failed")}), flush=True)
    print(f"report={output}", flush=True)
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
