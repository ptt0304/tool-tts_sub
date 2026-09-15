import io
import unittest
import wave

from local_tts.audio import fit_wav_duration


def wav_with_duration(seconds: float, sample_rate: int = 8_000) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(b"\x01\x00" * round(seconds * sample_rate))
    return output.getvalue()


class PreviewAudioTests(unittest.TestCase):
    def test_short_audio_is_padded_to_exact_duration(self):
        fitted = fit_wav_duration(wav_with_duration(0.5), 10.0)
        with wave.open(io.BytesIO(fitted), "rb") as reader:
            self.assertEqual(reader.getnframes(), 80_000)

    def test_long_audio_is_cropped_to_exact_duration(self):
        fitted = fit_wav_duration(wav_with_duration(12.0), 10.0)
        with wave.open(io.BytesIO(fitted), "rb") as reader:
            self.assertEqual(reader.getnframes(), 80_000)


if __name__ == "__main__":
    unittest.main()
