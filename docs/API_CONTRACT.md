# API contract

Default address: `http://127.0.0.1:8765`. No endpoint binds externally.

## Voice endpoints

- `GET /api/health` returns `{ "status": "READY", "voices": 1 }` after the single model instance loads.
- `GET /api/voices` returns `{ "voices": [Voice] }`.
- `GET /api/voices/{voice_id}` returns `Voice`, or `404` for an unknown ID.
- `POST /api/voices/{voice_id}/preview` returns an `audio/wav` body trimmed or
  padded to exactly 10 seconds. Every voice uses the same Vietnamese sample text.
  Only `READY` voices are accepted. Results are cached under `outputs/previews/`
  using the voice fingerprint and sample text, so a changed voice is regenerated.

A `Voice` has `voice_id`, `display_name`, `category`, `status`, `source`, and optional `status_reason`. Client code must select a `READY` voice only. A ZK candidate returned as `REQUIRES_REFERENCE` is intentionally not synthesizable or previewable.

For a reference voice, the engine uses the complete WAV to compute the speaker
embedding. Reference/style codes use the complete WAV up to 16.595 seconds; longer
code prompts are bounded because ONNX attention memory grows quadratically. The
paired TXT is required, validated, and included in enrollment-cache invalidation.
VieNeu v3 Turbo ONNX currently does not condition synthesis on reference transcript
text even though the compatibility API exposes a `ref_text` argument.

## Synthesis endpoints

`POST /api/tts/generate` body:

```json
{
  "segment_id": "000123",
  "speaker_id": "SPK_02",
  "voice_id": "vieneu_adam",
  "text": "Xin chào, [break] rất vui được gặp bạn.",
  "speed": 1.0,
  "pause_settings": {
    "space": 0.0,
    "comma": 0.25,
    "period": 0.45,
    "question": 0.55,
    "colon": 0.30,
    "ellipsis": 0.65,
    "newline": 0.50,
    "break_time": 1.0
  }
}
```

Successful response contains the original segment/speaker IDs, selected voice ID, absolute `audio_path`, duration, sample rate, and generation time. Files are written as `<safe segment_id>.wav` under the configured output directory.

`POST /api/tts/batch` body:

```json
{ "items": [{ "segment_id": "000123", "speaker_id": "SPK_02", "voice_id": "vieneu_adam", "text": "Xin chào", "speed": 1.0 }] }
```

Successful response preserves input order:

```json
{ "items": [{ "voice_id": "vieneu_ngoc_lan", "sample_rate": 48000, "audio_base64": "..." }] }
```

Input text must be nonempty and is limited to 10,000 characters per item; a batch is limited to 100 items. Batch work is sequential on CPU and held under the same application queue as a single generation request.

`pause_settings` is optional. When supplied, Local_TTS splits text at configured
punctuation, normalized horizontal whitespace, newlines, and case-insensitive
`[break]` markers, synthesizes each spoken part, and inserts PCM silence into the
resulting WAV. Values are seconds from `0` through `10`. One or more adjacent
spaces count as one marker; whitespace following punctuation does not override
that punctuation's pause. Straight/curly quotes and exclamation marks are ignored.
Adjacent non-space pause markers use the longest configured pause instead of
adding their durations. Punctuation remains in the text sent to the model for
prosody. Local_TTS trims model-generated edge silence and applies a short edge
fade before inserting the configured PCM silence, making each value the intended
total gap. Omitting the object preserves normal engine punctuation handling.

Errors use `{ "error": { "code": "...", "message": "..." } }`: `MODEL_NOT_READY`, `VOICE_NOT_FOUND`, `VOICE_NOT_READY`, `INVALID_TEXT`, `GENERATION_FAILED`, and `OUTPUT_WRITE_FAILED`.
