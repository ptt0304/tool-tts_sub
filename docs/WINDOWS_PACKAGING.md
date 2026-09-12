# Windows packaging

Use PyInstaller one-folder mode. ONNX Runtime and VieNeu include native DLLs; one-folder is less fragile than a single self-extracting executable.

Build from the project's provisioned Python environment:

```powershell
.\.build-env\Scripts\python.exe -m pip install pyinstaller onnxruntime librosa soundfile sea-g2p kaldi-native-fbank tokenizers huggingface_hub
.\scripts\build_windows.ps1
```

The current build environment uses Python 3.11. The build script bundles the
application and native CPU dependencies, then copies `models\huggingface` when
present. This keeps model weights outside the executable while allowing the
distributed folder to run offline.

The distribution is `dist\Local_TTS\Local_TTS.exe` with sibling `models`,
`voices`, `config`, `logs`, and `outputs` folders. Model weights are not
embedded into the EXE. For an offline deployment, provision the Hugging Face
cache under `models\huggingface\hub` before building. If that cache is absent,
the first run may download the supported VieNeu model when network access is
available.

`serve` is the default command, so double-clicking `Local_TTS.exe` starts the service. The service binds only to `127.0.0.1:8765`.
