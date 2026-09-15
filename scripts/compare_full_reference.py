from __future__ import annotations

import hashlib
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
VIENEU_SOURCE = ROOT.parent / "VieNeu-TTS" / "src"
sys.path.insert(0, str(VIENEU_SOURCE))

from vieneu import Vieneu  # noqa: E402


SAMPLE_TEXT = (
    "Xin chào, đây là phần nghe thử giọng nói tiếng Việt. "
    "Chúc bạn một ngày làm việc hiệu quả, vui vẻ và tràn đầy cảm hứng."
)
VOICE_IDS = ("xa_capcut_nu_hoat_ngon", "xa_ngoc_huyen")


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def write_pcm16(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    samples = np.asarray(audio, dtype=np.float32)
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm.tobytes())


def main() -> int:
    registry = json.loads((ROOT / "voices" / "registry.json").read_text(encoding="utf-8"))
    records = {record["voice_id"]: record for record in registry["voices"]}
    output_dir = ROOT / "outputs" / "experiments" / "full_reference"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading VieNeu v3 Turbo ONNX/CPU...", flush=True)
    load_started = time.perf_counter()
    tts = Vieneu(mode="v3turbo", backend="onnx", device="cpu", precision="fp32", threads=0)
    print(f"Model ready in {time.perf_counter() - load_started:.3f}s", flush=True)
    results: list[dict[str, object]] = []
    try:
        for voice_id in VOICE_IDS:
            record = records[voice_id]
            audio_path = Path(record["reference_audio"])
            text_path = Path(record["reference_text"])
            reference_text = text_path.read_text(encoding="utf-8-sig").strip()
            duration = wav_duration(audio_path)
            code_seconds = duration if duration <= 20.0 else 16.595
            item: dict[str, object] = {
                "voice_id": voice_id,
                "reference_audio": str(audio_path),
                "reference_audio_seconds": duration,
                "reference_text": str(text_path),
                "reference_text_chars": len(reference_text),
                "reference_text_sha256": hashlib.sha256(reference_text.encode("utf-8")).hexdigest(),
                "sample_text": SAMPLE_TEXT,
                "mode": "full_audio_ref_codes" if code_seconds == duration else "full_speaker_embedding_plus_bounded_ref_codes",
                "reference_code_seconds": code_seconds,
                "denoise": False,
                "note": "VieNeu ONNX accepts ref_text for API compatibility but does not condition inference on it.",
            }
            print(f"[{voice_id}] enrolling complete {duration:.3f}s WAV + paired TXT...", flush=True)
            started = time.perf_counter()
            try:
                # The speaker encoder can consume the complete file. Codec attention
                # grows quadratically and needs an 11+ GB contiguous buffer for the
                # 66-second CapCut clip, so bound only that style-code branch.
                speaker_emb = tts.engine.extract_speaker_emb(str(audio_path))
                _, ref_codes = tts.engine.prepare_reference(
                    str(audio_path),
                    denoise=False,
                    use_ref_codes=True,
                    max_seconds=code_seconds + 0.001,
                )
                item["enrollment_seconds"] = time.perf_counter() - started
                item["speaker_embedding_shape"] = list(np.asarray(speaker_emb).shape)
                item["reference_codes_shape"] = list(np.asarray(ref_codes).shape)
                print(
                    f"[{voice_id}] enrolled in {item['enrollment_seconds']:.3f}s; "
                    f"codes={item['reference_codes_shape']}",
                    flush=True,
                )
                synthesis_started = time.perf_counter()
                generated = tts.infer(
                    SAMPLE_TEXT,
                    voice={"speaker_emb": speaker_emb, "codes": ref_codes},
                    use_ref_codes=True,
                    temperature=0.4,
                    max_new_frames=300,
                    apply_watermark=False,
                )
                item["synthesis_seconds"] = time.perf_counter() - synthesis_started
                item["generated_audio_seconds"] = len(generated) / int(tts.sample_rate)
                output_path = output_dir / f"{voice_id}_full_reference.wav"
                write_pcm16(output_path, generated, int(tts.sample_rate))
                item["output"] = str(output_path.resolve())
                item["status"] = "OK"
                print(f"[{voice_id}] wrote {output_path}", flush=True)
            except Exception as error:
                item["status"] = "FAILED"
                item["error"] = f"{type(error).__name__}: {error}"
                print(f"[{voice_id}] FAILED: {item['error']}", flush=True)
            results.append(item)
    finally:
        tts.close()

    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {report_path}", flush=True)
    return 0 if all(item["status"] == "OK" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
