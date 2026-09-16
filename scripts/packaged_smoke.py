"""Launch the packaged executable from a different cwd and verify HTTP + WAV."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import wave

root = Path(__file__).resolve().parents[1]
app = root / "dist" / "Local_TTS"
env = dict(os.environ, HF_HUB_OFFLINE="1", PYTHONUTF8="1")
with (root / "packaged_smoke.log").open("w", encoding="utf-8") as log:
    process = subprocess.Popen([str(app / "Local_TTS.exe"), "serve"], cwd=root.parent, env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic() + 180
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"EXE exited {process.returncode}; see packaged_smoke.log")
            try:
                with urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=3) as response:
                    health = json.load(response)
                if health["status"] == "READY":
                    break
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError("Packaged server did not become ready")
            time.sleep(1)
        with urllib.request.urlopen("http://127.0.0.1:8765/", timeout=5) as response:
            operator_ui = response.read().decode("utf-8")
        assert "Cấu hình ngắt nghỉ" in operator_ui and "pauseBreak" in operator_ui
        with urllib.request.urlopen("http://127.0.0.1:8765/api/voices", timeout=5) as response:
            voices = json.load(response)["voices"]
        assert any(voice["voice_id"] == "piper_ngoc_huyen" and voice["status"] == "READY" for voice in voices)
        payload = {
            "segment_id": "packaged_pause_smoke",
            "speaker_id": "SPK_01",
            "voice_id": "vieneu_adam",
            "text": "Xin chào [break] đây là bài kiểm tra ngắt nghỉ.",
            "speed": 1.0,
            "pause_settings": {
                "comma": 0.15,
                "period": 0.20,
                "colon": 0.20,
                "ellipsis": 0.30,
                "newline": 0.40,
                "break_time": 1.00,
            },
        }
        request = urllib.request.Request("http://127.0.0.1:8765/api/tts/generate", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.load(response)
        with wave.open(result["audio_path"], "rb") as wav:
            assert wav.getnframes() > 0 and wav.getframerate() == result["sample_rate"]
            assert wav.getnframes() / wav.getframerate() >= 1.2
        piper_payload = {
            "segment_id": "packaged_piper_smoke",
            "speaker_id": "SPK_01",
            "voice_id": "piper_ngoc_huyen",
            "text": "Xin chào, đây là giọng Ngọc Huyền.",
            "speed": 1.0,
        }
        piper_request = urllib.request.Request("http://127.0.0.1:8765/api/tts/generate", data=json.dumps(piper_payload).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(piper_request, timeout=60) as response:
            piper_result = json.load(response)
        with wave.open(piper_result["audio_path"], "rb") as wav:
            assert wav.getnframes() > 0 and wav.getframerate() == 48000
        chunking_payload = {
            "segment_id": "packaged_chunking_smoke",
            "speaker_id": "SPK_01",
            "voice_id": "vieneu_adam",
            "text": "Mặc dù trời đã tối nhưng cô ấy vẫn đứng trước cửa chờ người mà cô đã không gặp suốt nhiều năm",
            "speed": 1.0,
            "pause_settings": {"space": 0, "comma": 0, "period": 0, "question": 0, "colon": 0, "ellipsis": 0, "newline": 0, "break_time": 0},
            "chunking_settings": {"preferred_syllables": 6, "soft_max_syllables": 8, "hard_max_syllables": 10, "minimum_chunk_syllables": 3, "merge_short_sentences": False, "crossfade_ms": 10},
        }
        chunking_request = urllib.request.Request("http://127.0.0.1:8765/api/tts/generate", data=json.dumps(chunking_payload).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(chunking_request, timeout=180) as response:
            chunking_result = json.load(response)
        with wave.open(chunking_result["audio_path"], "rb") as wav:
            assert wav.getnframes() > 0 and wav.getframerate() == 48000
        report = {"health": health, "generate": result, "piper_generate": piper_result, "chunking_generate": chunking_result}
        (root / "packaged_smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
    finally:
        process.terminate()
        process.wait(timeout=15)
