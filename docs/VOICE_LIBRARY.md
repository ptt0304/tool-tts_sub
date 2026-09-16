# Voice library

## Discovered ZK structure

Phase 1 inspection was limited to the flat ../ZKApps_v3_6/OVoice_Voices directory, TTS setup/dependency metadata, and ttsmodels metadata. Audio contents and model binaries were not read during that discovery phase.

- 51 WAV files and 52 TXT files: 51 matching basename pairs, no orphan WAV, and one unpaired zzz.txt.
- 50 pairs use vbee_<display name>.wav + vbee_<display name>.txt. Names preserve Vietnamese accents and spaces; some include style labels or versions such as v1, v2, and v2_beta.
- One pair is ZK_Nu_Long_Tieng.WAV + ZK_Nu_Long_Tieng.txt. Extension matching must be case-insensitive.
- Sample transcripts vbee_Anh Khôi.txt and ZK_Nu_Long_Tieng.txt contain Vietnamese prose. Their text matches the sampled zzz.txt contents. This does not prove transcript/audio alignment or uniqueness of the recordings.
- ../ZKApps_v3_6/ttsmodels contains NgocHuyen.onnx and NgocHuyen.onnx.json. JSON reports 22050 Hz, espeak voice vi, phoneme_type espeak, and num_speakers=1: evidence of a fixed, Piper-style model, not a reference recording.
- cai_thu_vien.bat includes a Torch/OmniVoice installation option with CUDA detection. That setup is not the dependency recipe for Local_TTS CPU inference. package_list.txt is an installed-package listing, not a complete compatibility guarantee; it lists soundfile 0.14.0.

## Voice categories

| Assets | Category | Phase 1 interpretation |
| --- | --- | --- |
| All 50 vbee_* pairs | Reference WAV/TXT candidates | File structure supports reference-audio reuse; untested |
| ZK_Nu_Long_Tieng pair | Reference WAV/TXT candidate | Same conditioning route; untested |
| zzz.txt | Unknown / incomplete asset | No matching WAV; do not expose as a selectable voice |
| NgocHuyen.onnx + metadata | Fixed Piper model | Exposed as `piper_ngoc_huyen` through the dedicated Piper backend |
| VieNeu built-in names | Presets | Upstream embeddings and codes; separate namespace from ZK |

No ZK preset-token mechanism was established from the inspected files. A filename prefix is provenance metadata, not proof of an engine or a speaker's gender.

## Stable voice_id proposal

Assign IDs once and persist them in the future registry. For ZK pairs, use zk_ plus a lowercase ASCII slug of the full basename: Unicode-normalize, remove Vietnamese diacritics, map đ to d, replace runs of punctuation/spaces with underscores, and retain source/style/version tokens. Example: vbee_Anh Khôi -> zk_vbee_anh_khoi; ZK_Nu_Long_Tieng -> zk_zk_nu_long_tieng.

On a slug collision, append a deterministic short digest of the original normalized basename; persist that assignment. Renaming files or display labels must not regenerate existing IDs. Use vieneu_ for native presets. Keep original names and relative asset paths separately. Do not derive voice_id from Cartoon_Sub speaker_id or guess gender from a name.

## Compatibility classification

V3 Turbo supports ref_audio directly, or encode_reference(ref_audio) -> speaker embedding + reference codes, which can be supplied as a voice dictionary. The current Local_TTS adapter requires a nonempty matching TXT for evidence and cache invalidation even though the ONNX inference call does not consume its text directly.

The ONNX loader reads audio with soundfile as float32, averages channels to mono, and resamples reference-code input to 48000 Hz. Reference preparation caps the clip at 8 seconds. Upstream recommends a short clean reference. Consequently, these WAV assets look structurally compatible, but format decoding, usable speech, conditioning quality, and successful output remain unverified for every pair.

| Status | Rule |
| --- | --- |
| REQUIRES_REFERENCE | No usable reference established yet; reason distinguishes missing_reference from unverified_reference. All 51 pairs remain here with reason unverified_reference until validated. This status does not mean their WAV files are absent. |
| READY | Asset validation and real inference with the selected backend succeed; output is nonempty and decodable. Record engine/model identity and evidence. |
| INVALID | Present asset fails decoding or validation, such as empty/unusable audio or broken metadata. Do not infer this merely from an unfamiliar name. |
| UNSUPPORTED | Representation cannot be used by any configured engine. |
| DISABLED | Explicitly excluded by registry configuration, with a reason. |

Keep category separate from status. The fixed model remains independent of VieNeu and is executed only by Piper. Do not convert or import its weights into VieNeu. zzz.txt stays outside the selectable inventory unless its intended role is established.

## 2026-09-15 local-library validation

The canonical application-local libraries are `XA_Voices/Việt Nam` (81
pairs), `XA_Voices/English` (18 pairs), and `ZK_Voices` (51 pairs plus one
unpaired TXT excluded from selection). Registry paths are relative to the
application root.

All 150 reference voices passed real VieNeu inference and generated-output
decoding. All 151 VieNeu runtime voices, including `vieneu_adam`, then passed
the actual HTTP preview endpoint with a decodable WAV of exactly 10 seconds.
`piper_ngoc_huyen` passed the equivalent source-adapter preview check, giving
152/152 successful previews and no server error log entries. Detailed results
are stored in `logs/diagnostics/preview_audit.json`.

## Remaining validation

Automated checks prove file pairing, inference, WAV decoding, and preview
delivery. Subjective similarity, pronunciation, signal quality, and whether
each display label matches the intended speaker still require human listening.

The Piper integration smoke on 2026-09-15 generated a nonempty, decodable mono
WAV from `NgocHuyen.onnx`: 3.416 seconds of service output at 48000 Hz, RTF
0.285 on the target machine. This is the inference evidence for exposing
`piper_ngoc_huyen` as READY; subjective listening quality remains an operator
check. The service normalizes the model's native 22050 Hz output to mono
PCM16/48000 Hz so Piper and VieNeu segments remain compatible in combined
batches.
