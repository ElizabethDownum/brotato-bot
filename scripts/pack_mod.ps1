<#
.SYNOPSIS
Packs mod\Ellie-BrotatoBot into build\BrotatoBot.zip, the file the Steam
Workshop uploader takes and the file sync_mod.ps1 installs.

.DESCRIPTION
The zip holds the loader's expected layout:

    .import/<asset>-<md5 of its res path>.stex   imported textures
    mods-unpacked/Ellie-BrotatoBot/<mod files>

with forward-slash entry names. The release build of the game cannot import
a PNG at runtime; it loads the pre-imported StreamTexture that the asset's
.import file names under res://.import/. So this script stages the mod in a
throwaway Godot project (build\import-stage, with the mod under
mods-unpacked\ so the res paths, and therefore the hashes, match the game),
runs the Godot 3.6 editor headlessly to import it, and packs every .stex it
produced. It fails if an .import file in the mod names a .stex that the
import did not produce (a stale hash, e.g. one copied from another mod).

The zip's basename, BrotatoBot, becomes the Workshop item title because the
game's upload utility (GodotWorkshopUtility.exe) calls setItemTitle with the
zip's basename on every upload. Prints "Packed <n> files and <m> imported
assets into <path>" and returns the path. Needs tools\godot (get_godot.ps1).
#>
[CmdletBinding()]
param(
    [string]$OutDir = (Join-Path $PSScriptRoot '..\build'),
    [int]$ImportTimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$repoRoot = Split-Path -Parent $PSScriptRoot
$source = (Join-Path $repoRoot 'mod\Ellie-BrotatoBot' | Resolve-Path).Path
$godot = Join-Path $repoRoot 'tools\godot\Godot_v3.6-stable_win64.exe'
if (-not (Test-Path -LiteralPath $godot)) {
    Write-Error "Godot not found at $godot. Run scripts\get_godot.ps1 first."
    exit 2
}
if (-not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}
$OutDir = (Resolve-Path -LiteralPath $OutDir).Path

# 1. Stage and import.
$stage = Join-Path $OutDir 'import-stage'
if (Test-Path -LiteralPath $stage) {
    Remove-Item -LiteralPath $stage -Recurse -Force
}
$stagedMod = Join-Path (Join-Path $stage 'mods-unpacked') 'Ellie-BrotatoBot'
New-Item -ItemType Directory -Path $stagedMod -Force | Out-Null
Copy-Item -Path (Join-Path $source '*') -Destination $stagedMod -Recurse -Force
Set-Content -LiteralPath (Join-Path $stage 'project.godot') -Value @(
    'config_version=4', '', '[application]', '', 'config/name="BrotatoBot import stage"')

# The .stex files the mod's .import files expect under res://.import/.
$expected = @{}
foreach ($importFile in Get-ChildItem -LiteralPath $source -Recurse -File -Filter '*.import') {
    foreach ($line in Get-Content -LiteralPath $importFile.FullName) {
        if ($line -match '^path="res://\.import/([^"]+)"') {
            $expected[$Matches[1]] = $importFile.FullName
        }
    }
}

# `--editor --quit` races the editor's filesystem scan ("Scan thread
# aborted"), so run the editor without --quit, wait until every expected
# .stex and its .md5 sidecar (written last) exist, then stop it.
$importDir = Join-Path $stage '.import'
$importLog = Join-Path $OutDir 'import-stage.log'
$proc = Start-Process -FilePath $godot `
    -ArgumentList @('--path', $stage, '--no-window', '--editor') `
    -NoNewWindow -PassThru -RedirectStandardOutput $importLog `
    -RedirectStandardError "$importLog.err"
$null = $proc.Handle
$deadline = (Get-Date).AddSeconds($ImportTimeoutSeconds)
$done = $false
while (-not $done -and (Get-Date) -lt $deadline -and -not $proc.HasExited) {
    Start-Sleep -Milliseconds 500
    $done = $true
    foreach ($name in $expected.Keys) {
        $stex = Join-Path $importDir $name
        $md5 = Join-Path $importDir ($name -replace '\.stex$', '.md5')
        if (-not ((Test-Path -LiteralPath $stex) -and (Test-Path -LiteralPath $md5))) {
            $done = $false
        }
    }
}
if (-not $proc.HasExited) {
    try { $proc.Kill() } catch { }
    $proc.WaitForExit(5000) | Out-Null
}

$stexFiles = @(Get-ChildItem -LiteralPath $importDir -File -Filter '*.stex' -ErrorAction SilentlyContinue)
$stexNames = @($stexFiles | ForEach-Object { $_.Name })

# 2. Every .import file in the mod must point at a .stex the import produced.
$missing = @()
foreach ($name in $expected.Keys) {
    if ($stexNames -notcontains $name) {
        $missing += "$($expected[$name]) -> $name"
    }
}
if ($missing.Count -gt 0) {
    Write-Error ("These .import files name a .stex the Godot import did not produce " +
        "within $ImportTimeoutSeconds s (stale hash? the hash is the md5 of the asset's " +
        "res:// path; see $importLog):`n" + ($missing -join "`n"))
    exit 1
}

# 3. Pack.
$zipPath = Join-Path $OutDir 'BrotatoBot.zip'
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
$files = Get-ChildItem -LiteralPath $source -Recurse -File
$zip = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($stex in $stexFiles) {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $zip, $stex.FullName, ".import/$($stex.Name)",
            [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($source.Length).TrimStart('\', '/') -replace '\\', '/'
        $entryName = "mods-unpacked/Ellie-BrotatoBot/$relative"
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $zip, $file.FullName, $entryName,
            [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
} finally {
    $zip.Dispose()
}

Write-Host "Packed $($files.Count) files and $($stexFiles.Count) imported assets into $zipPath"
$zipPath
