$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$stagingDist = Join-Path $root 'build\package-staging'
$stagedApp = Join-Path $stagingDist 'Local_TTS'
$finalApp = Join-Path $root 'dist\Local_TTS'
$runtimeRegistry = Join-Path $root 'dist\Local_TTS\voices\registry.json'
$runtimeRegistryBackup = Join-Path $root 'build\runtime-registry.json'
$buildPython = $null
foreach ($candidate in @(
  (Join-Path $root '.venv\Scripts\python.exe'),
  (Join-Path $root '.build-env\Scripts\python.exe')
)) {
  if (Test-Path -LiteralPath $candidate) {
    & $candidate -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -eq 0) { $buildPython = $candidate; break }
  }
}
if (-not $buildPython) { throw 'No usable Python environment with PyInstaller was found.' }
if (Test-Path -LiteralPath $runtimeRegistry) {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $runtimeRegistryBackup) | Out-Null
  Copy-Item -LiteralPath $runtimeRegistry -Destination $runtimeRegistryBackup -Force
}
if (Test-Path -LiteralPath $stagingDist) {
  Remove-Item -LiteralPath $stagingDist -Recurse -Force
}
$env:PYTHONPATH = "$root\src;$root\..\VieNeu-TTS\src"
& $buildPython -m PyInstaller --noconfirm --onedir --console --name Local_TTS `
  --distpath $stagingDist `
  --paths src `
  --paths ..\VieNeu-TTS\src `
  --collect-all vieneu `
  --collect-all onnxruntime `
  --collect-all sea_g2p `
  --collect-all librosa `
  --exclude-module torch `
  --exclude-module transformers `
  --exclude-module gradio `
  --exclude-module setuptools `
  --exclude-module win32com `
  --exclude-module pythoncom `
  --exclude-module pywintypes `
  --add-data "voices;voices" `
  --add-data "config;config" `
  src\local_tts\__main__.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: $LASTEXITCODE" }
New-Item -ItemType Directory -Force -Path $finalApp | Out-Null
Copy-Item -Path "$stagedApp\*" -Destination $finalApp -Recurse -Force
New-Item -ItemType Directory -Force -Path dist\Local_TTS\models,dist\Local_TTS\logs,dist\Local_TTS\outputs | Out-Null
Copy-Item -LiteralPath voices,config -Destination $finalApp -Recurse -Force
if (Test-Path -LiteralPath $runtimeRegistryBackup) {
  Copy-Item -LiteralPath $runtimeRegistryBackup -Destination $runtimeRegistry -Force
}
if (Test-Path -LiteralPath models\huggingface) {
  Copy-Item -LiteralPath models\huggingface -Destination dist\Local_TTS\models -Recurse -Force
}
$piperSource = Join-Path $root 'models\piper'
$piperDestination = Join-Path $finalApp 'models\piper'
if (-not (Test-Path -LiteralPath (Join-Path $piperSource 'runtime\piper.exe'))) {
  throw "Piper runtime not found: $piperSource\runtime"
}
if (-not (Test-Path -LiteralPath (Join-Path $piperSource 'NgocHuyen.onnx'))) {
  throw "Piper model not found: $piperSource"
}
New-Item -ItemType Directory -Force -Path $piperDestination | Out-Null
Copy-Item -Path (Join-Path $piperSource '*') -Destination $piperDestination -Recurse -Force
Copy-Item -LiteralPath (Join-Path $root 'XA_Voices') -Destination $finalApp -Recurse -Force
Copy-Item -LiteralPath (Join-Path $root 'ZK_Voices') -Destination $finalApp -Recurse -Force
