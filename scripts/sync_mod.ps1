<#
.SYNOPSIS
Packs mod\Ellie-BrotatoBot into a zip the Steam build of Brotato will load.

.DESCRIPTION
The Steam build runs from Brotato.pck with the mod loader's "steam" profile,
which has steam_workshop_enabled = true. In that mode the loader scans only
the Steam Workshop content folder for zips (<library>\steamapps\workshop\
content\1942280\<item id>\*.zip); it never reads <GameDir>\mods and cannot
open an unpacked res://mods-unpacked folder. So this script writes the zip
into a local, fake workshop item folder (default id 9999999999) that Steam
leaves alone because it is not a subscribed item.

The zip holds the loader's expected layout, mods-unpacked/Ellie-BrotatoBot/
<mod files>, with forward-slash entry names. Stale installs from earlier
methods (<GameDir>\mods\Ellie-BrotatoBot.zip and <GameDir>\mods-unpacked\
{Pasha-AutoBattler,Ellie-BrotatoBot}) are removed. Refuses to run while
Brotato.exe is running.
#>
[CmdletBinding()]
param(
    [string]$GameDir = 'D:\SteamLibrary\steamapps\common\Brotato',
    [string]$WorkshopDir = 'D:\SteamLibrary\steamapps\workshop\content\1942280',
    [string]$ItemId = '9999999999'
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

# Stale installs from the folder and <GameDir>\mods methods.
foreach ($name in 'Pasha-AutoBattler', 'Ellie-BrotatoBot') {
    $old = Join-Path (Join-Path $GameDir 'mods-unpacked') $name
    if (Test-Path -LiteralPath $old) {
        Remove-Item -LiteralPath $old -Recurse -Force
        Write-Host "Removed $old"
    }
}
$oldZip = Join-Path (Join-Path $GameDir 'mods') 'Ellie-BrotatoBot.zip'
if (Test-Path -LiteralPath $oldZip) {
    Remove-Item -LiteralPath $oldZip -Force
    Write-Host "Removed $oldZip"
}

$itemDir = Join-Path $WorkshopDir $ItemId
if (-not (Test-Path -LiteralPath $itemDir)) {
    New-Item -ItemType Directory -Path $itemDir -Force | Out-Null
}
$zipPath = Join-Path $itemDir 'Ellie-BrotatoBot.zip'
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
