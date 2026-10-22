<#
.SYNOPSIS
Copies mod\Ellie-BrotatoBot into the game's mods-unpacked folder.

.DESCRIPTION
Removes any existing Pasha-AutoBattler and Ellie-BrotatoBot folders under
<GameDir>\mods-unpacked, copies the repo's mod folder there and prints the number
of files copied. Refuses to run while Brotato.exe is running.
#>
[CmdletBinding()]
param(
    [string]$GameDir = 'D:\SteamLibrary\steamapps\common\Brotato'
)

$ErrorActionPreference = 'Stop'

if (Get-Process Brotato -ErrorAction SilentlyContinue) {
    Write-Error 'Brotato is running; quit the game before syncing the mod.'
    exit 1
}

$source = Join-Path $PSScriptRoot '..\mod\Ellie-BrotatoBot' | Resolve-Path
if (-not (Test-Path -LiteralPath $GameDir -PathType Container)) {
    Write-Error "Game directory not found: $GameDir"
    exit 1
}

$modsDir = Join-Path $GameDir 'mods-unpacked'
if (-not (Test-Path -LiteralPath $modsDir)) {
    New-Item -ItemType Directory -Path $modsDir | Out-Null
}

foreach ($name in 'Pasha-AutoBattler', 'Ellie-BrotatoBot') {
    $old = Join-Path $modsDir $name
    if (Test-Path -LiteralPath $old) {
        Remove-Item -LiteralPath $old -Recurse -Force
        Write-Host "Removed $old"
    }
}

$dest = Join-Path $modsDir 'Ellie-BrotatoBot'
Copy-Item -LiteralPath $source -Destination $dest -Recurse

$count = (Get-ChildItem -LiteralPath $dest -Recurse -File).Count
Write-Host "Copied $count files to $dest"
