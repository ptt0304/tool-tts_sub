# Local_TTS on Windows

Open `dist/Local_TTS/Local_TTS.exe`. Keep the complete folder, including `_internal`, together. Console status appears during model loading; the API listens on `127.0.0.1:8765`. Close the console or press Ctrl+C to exit.

Runtime folders beside the EXE:

- `config/settings.json`: port and model cache. Relative paths resolve against the EXE directory.
- `models/huggingface`: external Hugging Face cache. Weights are not embedded in the EXE.
- `voices/registry.json`: stored voice IDs, statuses, reference paths and validation evidence.
- `outputs`: generated WAV files.
- `logs/local_tts.log`: startup/model diagnostics.

This machine's distribution contains the existing CPU model cache. On a fresh installation without cache, the first startup downloads official artifacts from Hugging Face. Reference WAV paths point to the original ZK library; moving to another machine requires updating these paths or importing the library at its new location. Models and references are separate from the executable.

Incremental validation from the app directory:

```powershell
.\Local_TTS.exe validate-voices --voice-root "D:\path\OVoice_Voices" --registry voices/registry.json --infer --limit 1
```

Without `--infer`, only files are checked. Repeating the command retains successful unchanged reference validation and processes the next unvalidated voice. Only voices that pass real synthesis and output checks become READY; automated validation does not establish subjective voice similarity. Restart the service after updating the registry.

Build with independent Python 3.11+ and CPU dependencies in `.build-env`, then run `powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1`. The build uses the read-only sibling VieNeu source through PYTHONPATH, without installing/building inside that reference directory. PyInstaller one-folder avoids extracting large DLLs on each start. No CUDA or NVIDIA driver is required; Windows x64 and Microsoft VC++ runtime support are required by ONNX/native libraries.

API generation accepts segment_id, speaker_id, voice_id, text, speed. Speed changes use pitch-preserving post-processing. Batch results preserve all IDs including per-item errors. A repeat segment_id replaces its existing WAV. Use unique IDs per project to retain outputs.

Run `scripts/packaged_smoke.py` with the build Python while port 8765 is free to test the packaged executable from a different working directory, offline, using real inference. Results are stored in `packaged_smoke.json`.
