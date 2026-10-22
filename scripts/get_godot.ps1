# Downloads the Godot 3.6-stable Windows editor into tools/godot/ (gitignored)
# for headless GDScript tests. Idempotent: prints the exe path if present.
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$godotDir = Join-Path $repoRoot 'tools\godot'
$exeName  = 'Godot_v3.6-stable_win64.exe'
$exePath  = Join-Path $godotDir $exeName
$url      = 'https://github.com/godotengine/godot/releases/download/3.6-stable/Godot_v3.6-stable_win64.exe.zip'

if (Test-Path -LiteralPath $exePath) {
    Write-Output $exePath
    exit 0
}

New-Item -ItemType Directory -Force -Path $godotDir | Out-Null
$zipPath = Join-Path $godotDir "$exeName.zip"

Write-Host "Downloading $url"
Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
Expand-Archive -LiteralPath $zipPath -DestinationPath $godotDir -Force
Remove-Item -LiteralPath $zipPath -Force

if (-not (Test-Path -LiteralPath $exePath)) {
    Write-Error "Extraction did not produce $exePath"
    exit 1
}
Write-Output $exePath
exit 0
