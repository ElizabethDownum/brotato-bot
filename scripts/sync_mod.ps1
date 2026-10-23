<#
.SYNOPSIS
Packs mod\Ellie-BrotatoBot into <GameDir>\mods\Ellie-BrotatoBot.zip.

.DESCRIPTION
The Steam build of Brotato (a release export running from Brotato.pck) loads
mods only from zip files in <GameDir>\mods. Its loader cannot open an unpacked
res://mods-unpacked folder; that path only works when the extracted game
project runs under a Godot editor binary. The zip holds the loader's expected
layout, mods-unpacked/Ellie-BrotatoBot/<mod files>, with forward-slash entry
names.

Removes any stale Pasha-AutoBattler and Ellie-BrotatoBot folders under
<GameDir>\mods-unpacked and the previous zip, then prints the number of files
packed. Refuses to run while Brotato.exe is running.
#>
[CmdletBinding()]
param(
    [string]$GameDir = 'D:\SteamLibrary\steamapps\common\Brotato'
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

if (Get-Process Brotato -ErrorAction SilentlyContinue) {
    Write-Error 'Brotato is running; quit the game before syncing the mod.'
    exit 1
}

$source = (Join-Path $PSScriptRoot '..\mod\Ellie-BrotatoBot' | Resolve-Path).Path
if (-not (Test-Path -LiteralPath $GameDir -PathType Container)) {
    Write-Error "Game directory not found: $GameDir"
    exit 1
}

$unpackedDir = Join-Path $GameDir 'mods-unpacked'
foreach ($name in 'Pasha-AutoBattler', 'Ellie-BrotatoBot') {
    $old = Join-Path $unpackedDir $name
    if (Test-Path -LiteralPath $old) {
        Remove-Item -LiteralPath $old -Recurse -Force
        Write-Host "Removed $old"
    }
}

$modsDir = Join-Path $GameDir 'mods'
if (-not (Test-Path -LiteralPath $modsDir)) {
    New-Item -ItemType Directory -Path $modsDir | Out-Null
}
$zipPath = Join-Path $modsDir 'Ellie-BrotatoBot.zip'
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
    Write-Host "Removed $zipPath"
}

$files = Get-ChildItem -LiteralPath $source -Recurse -File
$zip = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)
try {
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

Write-Host "Packed $($files.Count) files into $zipPath"
