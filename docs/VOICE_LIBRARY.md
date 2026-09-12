# Voice library

## Discovered ZK structure

Inspection was limited to the flat ../ZKApps_v3_6/OVoice_Voices directory, TTS setup/dependency metadata, and ttsmodels metadata. Audio contents and model binaries were not read; no inference was run.

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
| NgocHuyen.onnx + metadata | Fixed model (Piper-style metadata) | Cannot be passed directly to VieNeu as a voice/reference |
| VieNeu built-in names | Presets | Upstream embeddings and codes; separate namespace from ZK |

No ZK preset-token mechanism was established from the inspected files. A filename prefix is provenance metadata, not proof of an engine or a speaker's gender.

## Stable voice_id proposal

Assign IDs once and persist them in the future registry. For ZK pairs, use zk_ plus a lowercase ASCII slug of the full basename: Unicode-normalize, remove Vietnamese diacritics, map đ to d, replace runs of punctuation/spaces with underscores, and retain source/style/version tokens. Example: vbee_Anh Khôi -> zk_vbee_anh_khoi; ZK_Nu_Long_Tieng -> zk_zk_nu_long_tieng.

On a slug collision, append a deterministic short digest of the original normalized basename; persist that assignment. Renaming files or display labels must not regenerate existing IDs. Use vieneu_ for native presets. Keep original names and relative asset paths separately. Do not derive voice_id from Cartoon_Sub speaker_id or guess gender from a name.

## Compatibility classification

V3 Turbo supports ref_audio directly, or encode_reference(ref_audio) -> speaker embedding + reference codes, which can be supplied as a voice dictionary. No reference transcript is required or consumed by this V3 path. Retain TXT files as provenance/optional validation material, not mandatory synthesis inputs. Do not confuse older VieNeu APIs that accept ref_text with this backend.

The ONNX loader reads audio with soundfile as float32, averages channels to mono, and resamples reference-code input to 48000 Hz. Reference preparation caps the clip at 8 seconds. Upstream recommends a short clean reference. Consequently, these WAV assets look structurally compatible, but format decoding, usable speech, conditioning quality, and successful output remain unverified for every pair.

| Status | Rule |
| --- | --- |
| REQUIRES_REFERENCE | No usable reference established yet; reason distinguishes missing_reference from unverified_reference. All 51 pairs remain here with reason unverified_reference until validated. This status does not mean their WAV files are absent. |
| READY | Asset validation and real inference with the selected VieNeu backend succeed; output is nonempty, finite, decodable, and reviewed for intelligibility and reference suitability. Record engine/model identity and evidence. |
| INVALID | Present asset fails decoding or validation, such as empty/unusable audio or broken metadata. Do not infer this merely from an unfamiliar name. |
| UNSUPPORTED | Representation cannot be used by the selected engine, such as the fixed NgocHuyen ONNX model as a VieNeu voice. |
| DISABLED | Explicitly excluded by registry configuration, with a reason. |

Keep category separate from status. Do not convert or execute the fixed model in V1 merely to obtain reference material. Do not import ZK model weights into VieNeu. zzz.txt stays outside the selectable inventory unless its intended role is established.

## Remaining validation

Audio encoding, duration, signal quality, distinct speaker identity, and transcript alignment have not been checked. No voice is READY based on this discovery. Later phases must prove each enabled ZK voice with actual CPU inference. Model provisioning, offline reference-encoder availability, and acceptable speed/quality on the target machine remain to be tested.
