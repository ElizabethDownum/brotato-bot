<#
.SYNOPSIS
Packs mod\Ellie-BrotatoBot into build\BrotatoBot.zip, the file the Steam
Workshop uploader takes and the file sync_mod.ps1 installs.

.DESCRIPTION
The zip holds the loader's expected layout, mods-unpacked/Ellie-BrotatoBot/
<mod files>, with forward-slash entry names. Its basename, BrotatoBot,
becomes the Workshop item title because the game's upload utility
(GodotWorkshopUtility.exe) calls setItemTitle with the zip's basename on
every upload. Prints "Packed <n> files into <path>" and returns the path.
#>
[CmdletBinding()]
param(
    [string]$OutDir = (Join-Path $PSScriptRoot '..\build')
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$source = (Join-Path $PSScriptRoot '..\mod\Ellie-BrotatoBot' | Resolve-Path).Path
if (-not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}
$OutDir = (Resolve-Path -LiteralPath $OutDir).Path
$zipPath = Join-Path $OutDir 'BrotatoBot.zip'
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
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
$zipPath
