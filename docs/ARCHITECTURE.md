# Architecture

## API -> Service -> Engine

```text
HTTP API -> TTSService -> RoutingEngine -> VieNeuEngine -> VieNeu-TTS
                                      `-> PiperEngine -> Piper CLI/ONNX
```

The API validates transport inputs and returns service results; it never imports or calls a synthesis backend directly. TTSService resolves voice IDs through VoiceRegistry, coordinates serialized generation, and returns WAV results. TTSEngine defines the synthesis boundary. RoutingEngine selects the backend from the registered `engine`; VieNeuEngine adapts the upstream SDK, while PiperEngine runs fixed Piper ONNX models through the bundled CLI.

Text chunking is provider-independent. `text_chunking` normalizes punctuation,
segments complete sentences, and only splits overlong sentences at scored
Vietnamese semantic/prosodic candidates. `audio.pauses` synthesizes those plans,
retains useful natural trailing silence, fills only a missing pause duration, and
uses a tiny configurable crossfade when adjacent semantic chunks have no pause.
Speaker detection, emotion classification, subtitle timing, and overlap remain
owned by Cartoon_Sub and are not inferred inside a TTS provider.

V1 routes: GET /api/health, GET /api/voices, GET /api/voices/{voice_id}, POST /api/tts/generate, POST /api/tts/batch. CPU batch requests are processed sequentially; different voice IDs are resolved per item.

## Model lifecycle

Create one V3 Turbo CPU/ONNX instance during application startup and reuse it for all requests. Validate the bundled Piper runtime, eSpeak data, model, and config at the same startup boundary. Use one application process/worker. Close both backends on shutdown. Health must distinguish initialization, readiness, and failure.

Complete required model provisioning before reporting synthesis readiness. Upstream can download missing artifacts and lazily initialize reference encoders; prepare enabled reference voices during startup where practical. Do not create a model per request. A service-level lock covers reference preparation and inference, including batch work. Upstream internal generation locks do not establish safety for the entire SDK lifecycle.

## VoiceRegistry

VoiceRegistry owns stable voice IDs, display names, source provenance, voice category, reference paths or preset names, status, and validation evidence. It is separate from the engine. Engine-specific embeddings/reference codes belong to the engine adapter and are derived from registry assets; clients never supply upstream preset internals.

Only validated voices can be selected for synthesis. Unknown, invalid, unsupported, disabled, and unverified references must produce explicit service errors rather than silently falling back to a default voice. See VOICE_LIBRARY.md for status rules.

## Ownership boundary with Cartoon_Sub

Local_TTS owns text + voice_id -> WAV. Cartoon_Sub owns speaker detection, speaker_id, translation, timestamps, overlap, timeline, audio placement, audio mixing, and video rendering. Cartoon_Sub maintains mappings such as SPK_01 -> zk_female_a and knows only voice_id and the REST API.

Existing ZK reference assets may condition inference. V1 has no new voice-cloning UI/workflow and no training or fine-tuning.

## Local CPU target

Windows on Intel Core Ultra 5 125H, without assuming NVIDIA hardware or CUDA. Explicitly select v3turbo, backend=onnx, device=cpu, precision=fp32 for the initial baseline. ONNX sessions use CPUExecutionProvider. INT8 and thread tuning require later hardware validation.

Bind to 127.0.0.1:8765 only. The future Local_TTS.exe wraps the same service. Local synthesis does not imply an offline first startup: model provisioning/cache completeness must be addressed before executable packaging.
