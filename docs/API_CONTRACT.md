# API contract

Default address: `http://127.0.0.1:8765`. No endpoint binds externally.

## Voice endpoints

- `GET /api/health` returns `{ "status": "READY", "voices": 1 }` after the single model instance loads.
- `GET /api/voices` returns `{ "voices": [Voice] }`.
- `GET /api/voices/{voice_id}` returns `Voice`, or `404` for an unknown ID.

A `Voice` has `voice_id`, `display_name`, `category`, `status`, `source`, and optional `status_reason`. Client code must select a `READY` voice only. A ZK candidate returned as `REQUIRES_REFERENCE` is intentionally not synthesizable.

## Synthesis endpoints

`POST /api/tts/generate` body:

```json
{ "segment_id": "000123", "speaker_id": "SPK_02", "voice_id": "vieneu_adam", "text": "Xin chào", "speed": 1.0 }
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

Errors use `{ "error": { "code": "...", "message": "..." } }`: `MODEL_NOT_READY`, `VOICE_NOT_FOUND`, `VOICE_NOT_READY`, `INVALID_TEXT`, `GENERATION_FAILED`, and `OUTPUT_WRITE_FAILED`.
