# Local_TTS

Local_TTS is a Windows-local Vietnamese text-to-speech service for application
integration. It accepts **text + voice ID** through a loopback REST API and
returns a WAV file. The service uses VieNeu V3 Turbo and Piper through ONNX CPU,
so it does not require an NVIDIA GPU or CUDA.

Cartoon_Sub is the primary client. Local_TTS only owns `text + voice_id → WAV`.
Cartoon_Sub owns speaker detection, translation, timestamps, timeline,
placement, mixing, and video rendering.

## Features

- Windows executable or Python service; default bind is `127.0.0.1:8765`.
- VieNeu is initialized once per process; Piper assets are validated at startup.
- Serialized generation and output writing for safe CPU inference.
- VieNeu preset/reference voices plus the fixed Ngọc Huyền Piper model.
- Stable voice IDs, persisted voice status, and validation evidence.
- Deterministic, safe WAV output names based on `segment_id`.
- Single and sequential batch generation endpoints.
- Local browser UI: select an SRT and ready voice to create one WAV per cue.
- One-click 10-second preview for every usable voice, using the same sample text.
- High-fidelity reference enrollment: complete WAV speaker embedding plus reference
  codes (bounded to 16.595 seconds for long clips to keep ONNX memory safe).
- No voice-cloning UI, fine-tuning, or training in V1.

## Requirements

The packaged application requires Windows 10/11 x64 and a Microsoft Visual
C++ runtime compatible with ONNX Runtime. It targets an Intel Core Ultra 5
125H using ONNX `CPUExecutionProvider` and fp32. No CUDA is required.

For source development, use Python 3.11 or newer. The verified build uses
Python 3.11. Reference-voice synthesis can be much slower than audio duration
on CPU.

## Distribution layout

Keep the complete `dist/Local_TTS` folder together:

```text
Local_TTS/
├── Local_TTS.exe
├── _internal/                 # PyInstaller runtime and native dependencies
├── config/settings.json       # localhost port and model-cache location
├── models/huggingface/hub/    # external VieNeu model cache
├── models/piper/              # Piper runtime, eSpeak data, and fixed model
├── voices/
│   ├── registry.json          # voice metadata and validation status
│   └── backups/               # registry backups
├── outputs/
│   ├── *.wav                  # generated WAV files (compatible public location)
│   ├── previews/              # cached 10-second voice previews
│   ├── validation/            # temporary voice-validation artifacts
│   └── diagnostics/           # audio retained for diagnosis
└── logs/
    ├── local_tts.log          # normal application log
    └── diagnostics/           # launch/build diagnostic logs
```

Model weights are external to `Local_TTS.exe`. If
`models/huggingface/hub` is present, the service can start offline. If it is
absent, VieNeu may download official artifacts during first startup when the
machine has network access.

## Start the desktop application and service

Double-click `Local_TTS.exe`, or run:

```powershell
cd D:\path\to\Local_TTS
.\Local_TTS.exe
```

The executable loads the model, starts the localhost API, and opens the local
operator UI in the default browser at `http://127.0.0.1:8765/`. The UI provides
direct text or SRT/TXT input, voice selection, speed, configurable pauses,
batch generation, and a **Nghe thử 10s** button beside every usable voice. All preview
buttons use one common Vietnamese sample; the first request is generated lazily
and later requests reuse the cached WAV. The console
also reports model status:

```text
Server: Running
Address: 127.0.0.1:8765
Engines: VieNeu + Piper | Backend: ONNX CPU
Model: Ready
Voices: N ready
```

When Piper assets are present, the ready-voice list includes
`piper_ngoc_huyen`. Requests keep the same REST shape; Local_TTS routes this
voice to Piper and the existing preset/reference voices to VieNeu.

Press `Ctrl+C` or close the console to stop the service. Logs are written to
`logs/local_tts.log`.

### Create WAV files from an SRT

1. Start `Local_TTS.exe` and wait for the browser UI to show **Model: READY**.
2. Choose an `.srt` file and select a `READY` voice.
3. Set an output prefix and optional speed (0–3).
4. Optionally open **Cấu hình ngắt nghỉ** to set pauses for punctuation,
   newlines, or the `[break]` marker.
5. Select **Tạo WAV**.

The application creates `srt_000001.wav`, `srt_000002.wav`, and so on from the
SRT cue numbers in `outputs/`. It does not place or mix audio on a timeline.

Default configuration in `config/settings.json`:

```json
{
  "port": 8765,
  "model_cache": "models/huggingface",
  "tts_chunking": {
    "preferred_syllables": 16,
    "soft_max_syllables": 24,
    "hard_max_syllables": 32,
    "minimum_chunk_syllables": 3,
    "merge_short_sentences": false,
    "crossfade_ms": 10
  }
}
```

Paths in this file resolve relative to the executable directory, not the
current working directory.

## REST API

Base URL: `http://127.0.0.1:8765`

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Model state and ready-voice count |
| `GET` | `/api/voices` | Registered voice records |
| `GET` | `/api/voices/{voice_id}` | One voice record |
| `POST` | `/api/voices/{voice_id}/preview` | Playable, exact 10-second WAV preview |
| `POST` | `/api/tts/generate` | Generate one WAV file |
| `POST` | `/api/tts/batch` | Generate a sequential batch |

### Check health

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/health
```

Example:

```json
{ "status": "READY", "voices": 1 }
```

### List voices

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/voices
```

The operator UI lists the built-in preset and every imported ZK reference. A
ZK reference begins as `DISABLED`; select it and use **Xác thực & bật giọng ZK
đã chọn** to run a short real inference. Only a successful result changes it to
`READY` and persists that evidence in the registry.

### Generate one WAV

```powershell
$body = @{
  segment_id = "000123"
  speaker_id = "SPK_02"
  voice_id   = "vieneu_adam"
  text       = "Chuyện này không liên quan đến cô."
  speed      = 1.0
  pause_settings = @{
    space = 0.0; comma = 0.25; period = 0.45; question = 0.55
    colon = 0.30; ellipsis = 0.65; newline = 0.50; break_time = 1.0
  }
  chunking_settings = @{
    preferred_syllables = 16; soft_max_syllables = 24
    hard_max_syllables = 32; minimum_chunk_syllables = 3
    merge_short_sentences = $false; crossfade_ms = 10
  }
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8765/api/tts/generate `
  -ContentType "application/json" -Body $body
```

Example result:

```json
{
  "segment_id": "000123",
  "speaker_id": "SPK_02",
  "voice_id": "vieneu_adam",
  "audio_path": "D:\\Local_TTS\\outputs\\000123.wav",
  "duration": 2.08,
  "sample_rate": 48000,
  "generation_time": 1.97
}
```

`segment_id` accepts letters, digits, `_`, and `-` only. Relative paths,
absolute paths, unsafe characters, and Windows device names are rejected.
Reusing a valid ID replaces its corresponding WAV.

Pause configuration is optional. The browser UI stores it locally and sends it
with each job. Insert `[break]` anywhere in text for the configured explicit
pause. Commas, colons, and horizontal whitespace stay inside a complete sentence
and do not create isolated TTS calls. Quotes, questions, exclamations, and
ellipses are preserved for model prosody. Model-generated trailing silence counts
toward the configured boundary pause, so Local_TTS inserts only the missing
duration rather than adding a second full pause. A zero-pause semantic split uses
the configured tiny crossfade inside retained edge-silence margins.

Chunking defaults come from `config/settings.json`; API callers may override
them per request with `chunking_settings`. Complete sentences are retained by
default. Only sentences beyond `hard_max_syllables` are split, using scored
Vietnamese clause/conjunction boundaries rather than a character limit.
API clients can omit `pause_settings` to retain VieNeu's normal handling.

### Generate a batch

Send this payload to `POST /api/tts/batch`:

```json
{
  "items": [
    {
      "segment_id": "000123",
      "speaker_id": "SPK_02",
      "voice_id": "vieneu_adam",
      "text": "Xin chào.",
      "speed": 1.0
    }
  ]
}
```

Batch items are processed sequentially and returned in the original order. A
failed item contains its own `error` object; subsequent items still run. Text
is limited to 10,000 characters per item and batches to 100 items. `speed`
must be greater than zero and no more than `3.0`.

### Error response

```json
{ "error": { "code": "VOICE_NOT_READY", "message": "voice is not ready for synthesis" } }
```

Codes: `MODEL_NOT_READY`, `VOICE_NOT_FOUND`, `VOICE_NOT_READY`,
`INVALID_TEXT`, `GENERATION_FAILED`, and `OUTPUT_WRITE_FAILED`. Python
tracebacks are never returned to API callers. See
[docs/API_CONTRACT.md](docs/API_CONTRACT.md) for the formal contract.

## Voice library

Local_TTS imports stable IDs at discovery time; callers must not derive an ID
from a display name. For example, `vbee_Anh Khôi` becomes
`zk_vbee_anh_khoi`.

Reference assets live inside `XA_Voices` and `ZK_Voices`. Registry paths are
stored relative to the application root so the complete Local_TTS folder can be
moved without invalidating every voice. The current VieNeu adapter requires a
nonempty WAV/TXT pair, uses the WAV for speaker/style conditioning, and retains
the TXT for pairing and cache invalidation.

The validated inventory is 81 `xa_*` Vietnamese voices, 18 `xa_en_*` English
reference voices, and 51 `zk_*` voices. Runtime also adds the `vieneu_adam`
preset and the fixed `piper_ngoc_huyen` model, for 152 READY voices total.

| Status | Meaning |
| --- | --- |
| `READY` | Real inference and generated-output validation succeeded |
| `DISABLED` | Valid source, deliberately not enabled or awaiting inference |
| `INVALID` | Missing, corrupt, or incomplete source asset |
| `UNSUPPORTED` | Incompatible with the selected engine |
| `REQUIRES_REFERENCE` | Imported candidate awaiting reference material |

Validate both local reference libraries incrementally:

```powershell
.\Local_TTS.exe validate-voices `
  --zk-voice-root ZK_Voices `
  --xa-voice-root XA_Voices `
  --registry voices\registry.json `
  --infer --limit 1
```

Without `--infer`, only files are checked. With it, the model starts once and
validates up to `--limit` eligible voices; results are cached in
`voices/registry.json`. Restart the service after registry changes. This check
proves audio generation, not subjective speaker similarity. See
[docs/VOICE_LIBRARY.md](docs/VOICE_LIBRARY.md) for the validation evidence and
voice-ID rules.

## Source development

`../VieNeu-TTS` and `../ZKApps_v3_6` are read-only reference repositories.
Create an isolated environment in Local_TTS:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

To use the checked VieNeu source in the same workspace:

```powershell
$env:PYTHONPATH = "$PWD\src;$PWD\..\VieNeu-TTS\src"
python -m local_tts
```

Run targeted tests:

```powershell
python -m unittest discover -s tests -v
```

Unit tests use `MockTTSEngine` and do not download models. Real engine smoke
tests require ONNX dependencies and a populated model cache.

## Build and verify Windows package

Use an independent build environment:

```powershell
py -3.11 -m venv .build-env
.\.build-env\Scripts\Activate.ps1
python -m pip install pyinstaller onnxruntime librosa soundfile sea-g2p kaldi-native-fbank tokenizers huggingface_hub
.\scripts\build_windows.ps1
```

The script creates `dist/Local_TTS`, packages the ONNX CPU runtime in
one-folder mode, and copies `voices`, `config`, and an existing
`models/huggingface` cache. Verify it from a different working directory:

```powershell
.\.build-env\Scripts\python.exe .\scripts\packaged_smoke.py
```

The smoke test enforces offline mode, waits for `/api/health`, then creates a
real WAV through the packaged EXE. Ensure port `8765` is free. See
[docs/WINDOWS_PACKAGING.md](docs/WINDOWS_PACKAGING.md) for deployment details.

## Operations and boundaries

- Run one Local_TTS process for a given machine and port: every process loads
  its own ONNX model and uses substantial memory.
- CPU batches are intentionally sequential. Queue work from Cartoon_Sub when
  a predictable render pipeline is needed.
- `audio_path` is an absolute local path for same-machine callers. Do not
  expose this API beyond localhost.
- Back up `voices/registry.json` before moving/replacing voice files.
- Define a retention policy for `outputs`, which can grow quickly.

```text
HTTP API → TTSService → TTSEngine → VieNeuEngine → VieNeu-TTS
                 ↘ VoiceRegistry
```

Further project constraints are documented in [AGENTS.md](AGENTS.md),
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/INDEX.md](docs/INDEX.md).
