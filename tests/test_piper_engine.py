import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import wave

from local_tts.engine import PiperEngine
from local_tts.models import Voice, VoiceCategory, VoiceStatus
from local_tts.voice import VoiceRegistry


class PiperEngineTests(unittest.TestCase):
    def test_synthesize_invokes_cli_and_reads_wav_metadata(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "piper.exe"
            espeak_data = root / "espeak-ng-data"
            model = root / "voice.onnx"
            config = root / "voice.onnx.json"
            executable.write_bytes(b"exe")
            espeak_data.mkdir()
            model.write_bytes(b"onnx")
            config.write_text("{}", encoding="utf-8")
            voice = Voice(
                "piper_test", "Piper test", VoiceStatus.READY, "test", "piper",
                category=VoiceCategory.FIXED_MODEL,
                metadata={"model_path": str(model), "config_path": str(config)},
            )
            engine = PiperEngine(
                VoiceRegistry([voice]), root / "outputs",
                executable=executable, espeak_data=espeak_data,
            )
            engine.start()

            def fake_run(command, **kwargs):
                output = Path(command[command.index("--output_file") + 1])
                with wave.open(str(output), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(22050)
                    wav.writeframes(b"\0\0" * 22050)
                return subprocess.CompletedProcess(command, 0, b"", b"")

            with patch("local_tts.engine.piper_engine.subprocess.run", side_effect=fake_run) as run:
                result = engine.synthesize("Xin chào", "piper_test", speed=2.0)

            self.assertEqual(result.sample_rate, 48000)
            self.assertEqual(result.audio_duration_seconds, 1.0)
            with wave.open(str(result.output_path), "rb") as wav:
                self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (1, 2, 48000))
            command = run.call_args.args[0]
            self.assertEqual(command[command.index("--length_scale") + 1], "0.5")
            self.assertEqual(run.call_args.kwargs["input"], "Xin chào\n".encode("utf-8"))
            self.assertEqual(run.call_args.kwargs["timeout"], 120)


if __name__ == "__main__":
    unittest.main()
