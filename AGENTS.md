# Local_TTS project instructions

## Scope and phase discipline

- Modify only Local_TTS. ../VieNeu-TTS and ../ZKApps_v3_6 are read-only reference sources.
- Implement only the requested phase, then stop. Phase 1 was documentation only; later implementation work must preserve its verified source findings.
- Local_TTS owns text + voice_id -> WAV. Cartoon_Sub owns speaker detection/IDs, translation, timestamps, overlap, timeline, placement, mixing, and video rendering.
- Target Windows, Intel Core Ultra 5 125H, CPU/ONNX; no NVIDIA or CUDA requirement.
- Existing reference voices are allowed. New voice-cloning workflows and training/fine-tuning are outside V1.

## Task routing and context budget

- Start with docs/INDEX.md; read docs/ARCHITECTURE.md for API/service/engine or lifecycle tasks, and docs/VOICE_LIBRARY.md for voice tasks.
- Read only the relevant future implementation directory: api for HTTP, service for orchestration, engine for VieNeu integration, voice for registry, audio for WAV handling, and models for shared request/response types.
- Start from explicitly named paths. Never scan the whole workspace or recursively inspect ZKApps_v3_6.
- Read at most 3-6 source files before deciding which additional evidence is necessary. Search symbols in selected files; avoid dumping large files or asset lists.
- Skip .venv, package environments, caches, generated audio, model weights, binaries, and .pyd contents unless specifically needed for the current task.
- VieNeu inspection is limited to inference entrypoints, initialization, CPU/ONNX backend, voice conditioning, and output handling.
- ZK inspection is limited to OVoice_Voices, TTS setup/configuration, TTS model metadata, dependency metadata, and necessary ZK_CLONE_VOICE names/strings. Do not inspect unrelated video, hardsub, or translation modules.

## Implementation guardrails for later phases

- HTTP API -> TTSService -> TTSEngine -> VieNeuEngine -> VieNeu. API handlers never call VieNeu directly.
- VoiceRegistry remains independent of the engine and exposes stable voice IDs and evidence-based statuses.
- Load one engine at startup and reuse it. Serialize reference preparation and inference; avoid multiple server workers each loading a model.
- Bind only to 127.0.0.1:8765 by default.
- Never mark a ZK voice READY without successful real inference. File pairing alone is insufficient.
- Run targeted tests for changed behavior only. Do not run the full suite unless shared/core models require it. Do not download models or run inference during documentation-only work.
- No unrelated refactors or empty abstractions. Keep documentation aligned with verified source behavior and distinguish proposals from observations.
- Keep final reports concise and follow the phase-specific reporting format.
