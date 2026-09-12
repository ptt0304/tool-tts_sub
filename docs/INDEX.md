# Local_TTS documentation

- [Architecture](ARCHITECTURE.md): boundaries, lifecycle, registry responsibilities, and Windows CPU target.
- [API contract](API_CONTRACT.md): V1 request, response, status, and error behavior.
- [Voice library](VOICE_LIBRARY.md): ZK asset structure, categories, stable IDs, and compatibility rules.
- [Project instructions](../AGENTS.md): task routing and context limits.

Phase 1 created the discovery documentation. The subsequent implementation phase adds a local API/service/engine skeleton, but performs no dependency installation, model download, or real inference validation. No workspace-root AGENTS.md or ancestor AGENTS.md was found at inspection time; the user's project instructions govern this discovery. Reference repositories were not modified.

## VieNeu source discovery

These findings describe the local checkout (pyproject.toml version 3.6.4), not a remotely verified release. Paths below are relative to the workspace root.

| Question | Finding and source |
| --- | --- |
| Open-source V3 entrypoint | from vieneu import Vieneu, then Vieneu(mode="v3turbo", backend="onnx", device="cpu", precision="fp32"). src/vieneu/__init__.py exports the factory; factory.py selects V3TurboVieNeuTTS. examples/main_v3turbo.py demonstrates infer/save. All paths in this row are under VieNeu-TTS/. |
| Initialization | VieNeu-TTS/src/vieneu/v3turbo.py: V3TurboVieNeuTTS.__init__ constructs OnnxV3LiteEngine. Explicit device=cpu avoids automatic Torch device probing. Default backbone is pnnbao-ump/VieNeu-TTS-v3-Turbo; fp32 selects onnx_update, int8 selects onnx_int8. |
| Download/cache | VieNeu-TTS/src/vieneu/_v3_turbo_engine/onnx_runtime_lite.py fetches graph/config/tokenizer/embedding artifacts via hf_hub_download; no explicit cache_dir or revision is passed, so caching is delegated to Hugging Face configuration. Codec artifacts come from OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX. Required graph failures propagate. |
| Local/offline caveat | onnx_dir bypasses backbone graph fetching, not all downloads. Codec files are fetched separately; codec_dir exists on the lower engine but is not forwarded by this SDK constructor. Denoiser resolution is attempted at initialization and failure is tolerated. Speaker encoder loads lazily on first reference use; codec encoder files are fetched at startup but its ONNX session is lazy. Repository voice overrides may also be fetched. Full offline packaging is not established. |
| Presets | v3turbo.py loads assets/voices_v3_turbo.json plus optional repository overrides. list_preset_voices() returns label/name pairs; get_preset_voice() returns metadata, a 192-dimensional speaker embedding, and reference codes. infer(text, voice=<name or dictionary>) selects one; omitted voice uses the default. |
| Reference conditioning | v3turbo.py: infer(text, ref_audio=<path>) or encode_reference(path). The reference takes precedence over a preset. Backend prepare_reference extracts speaker embedding and optional reference codes, with optional denoising. No transcript required. |
| Audio output | infer returns a mono NumPy waveform at 48000 Hz; ONNX decoding produces float32. Empty normalized text yields an empty float32 array. VieNeu-TTS/src/vieneu/base.py save writes via soundfile using self.sample_rate. WAV encoding subtype is not explicitly specified by that method. |
| Batch | v3turbo.py infer_batch(texts, voice=.../ref_audio=...) returns waveforms in input order with one shared voice. CPU/ONNX executes sequentially, without GPU batching acceleration. Mixed-voice service batches require per-item resolution or grouping in a later phase. |
| Thread safety | onnx_runtime_lite.py uses threading.RLock around generation sections. Reference encoder lazy initialization and SDK preset state are outside a single encompassing request lock. Full concurrent SDK safety is not established; serialize complete service synthesis operations. |

## Follow-up scope

Before implementation, resolve model/cache provisioning for Windows and the eventual executable. Before enabling any ZK voice, validate its audio and run real inference. Benchmark fp32 on the target CPU before choosing INT8 or custom thread counts. No production API contract file or executable scaffold is created in Phase 1.
