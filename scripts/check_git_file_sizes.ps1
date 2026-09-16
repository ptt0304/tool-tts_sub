param(
  [long]$MaxBytes = 100000000
)

$ErrorActionPreference = 'Stop'

$root = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not $root) {
  throw 'This script must run inside the Local_TTS Git repository.'
}

$oversized = @()
$visiblePaths = @(& git -C $root ls-files --cached --others --exclude-standard)
foreach ($relativePath in $visiblePaths) {
  $path = Join-Path $root $relativePath
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
  $file = Get-Item -LiteralPath $path
  if ($file.Length -gt $MaxBytes) {
    $oversized += [pscustomobject]@{
      SizeMB = [math]::Round($file.Length / 1MB, 1)
      Path = $relativePath
    }
  }
}

if ($oversized.Count) {
  Write-Error ("Files larger than {0:N1} MB are visible to Git:`n{1}" -f (
    $MaxBytes / 1MB
  ), ($oversized | Format-Table -AutoSize | Out-String))
  exit 1
}

Write-Host ("OK: no Git-visible file exceeds {0:N0} bytes ({1:N1} MiB)." -f $MaxBytes, ($MaxBytes / 1MB))
