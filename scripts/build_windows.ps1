$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONPATH = "$root\src;$root\..\VieNeu-TTS\src"
.\.build-env\Scripts\python.exe -m PyInstaller --noconfirm --onedir --console --name Local_TTS `
  --paths src `
  --paths ..\VieNeu-TTS\src `
  --collect-all vieneu `
  --collect-all onnxruntime `
  --collect-all sea_g2p `
  --collect-all librosa `
  --exclude-module torch `
  --exclude-module transformers `
  --exclude-module gradio `
  --add-data "voices;voices" `
  --add-data "config;config" `
  src\local_tts\__main__.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: $LASTEXITCODE" }
New-Item -ItemType Directory -Force -Path dist\Local_TTS\models,dist\Local_TTS\logs,dist\Local_TTS\outputs | Out-Null
Copy-Item -LiteralPath voices,config -Destination dist\Local_TTS -Recurse -Force
if (Test-Path -LiteralPath models\huggingface) {
  Copy-Item -LiteralPath models\huggingface -Destination dist\Local_TTS\models -Recurse -Force
}
