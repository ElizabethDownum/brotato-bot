<#
.SYNOPSIS
Packs mod\Ellie-BrotatoBot into a zip the Steam build of Brotato will load.

.DESCRIPTION
The Steam build runs from Brotato.pck with the mod loader's "steam" profile
(steam_workshop_enabled = true). Brotato's fork of the loader then loads
zips only from Steam Workshop item folders whose id is in the player's
subscription list (Platform.get_subscribed_mods, i.e.
Steam.getSubscribedItems). It never reads <GameDir>\mods, cannot open an
unpacked res://mods-unpacked folder, and skips workshop folders that are
not subscribed. There is no CLI switch for any of this.

So this script writes the zip into the folder of a Workshop item the owner
is subscribed to. The default is Botato (item 2965027290), the mod this one
derives from. Steam fills that folder on subscription; the script renames
any other zip in it to *.zip.disabled so only this mod loads from it. Steam
only rewrites the folder when the item itself updates, after which the
script simply has to run again.

The zip holds the loader's expected layout, mods-unpacked/Ellie-BrotatoBot/
<mod files>, with forward-slash entry names. Stale installs from earlier
methods (<GameDir>\mods\Ellie-BrotatoBot.zip, <GameDir>\mods-unpacked\
{Pasha-AutoBattler,Ellie-BrotatoBot} and the fake item folder 9999999999)
are removed. Refuses to run while Brotato.exe is running.
#>
[CmdletBinding()]
param(
    [string]$GameDir = 'D:\SteamLibrary\steamapps\common\Brotato',
    [string]$WorkshopDir = 'D:\SteamLibrary\steamapps\workshop\content\1942280',
    [string]$ItemId = '2965027290'
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

# Stale installs from the folder, <GameDir>\mods and fake-item methods.
foreach ($name in 'Pasha-AutoBattler', 'Ellie-BrotatoBot') {
    $old = Join-Path (Join-Path $GameDir 'mods-unpacked') $name
    if (Test-Path -LiteralPath $old) {
        Remove-Item -LiteralPath $old -Recurse -Force
        Write-Host "Removed $old"
    }
}
foreach ($old in @((Join-Path (Join-Path $GameDir 'mods') 'Ellie-BrotatoBot.zip'),
                   (Join-Path $WorkshopDir '9999999999'))) {
    if (Test-Path -LiteralPath $old) {
        Remove-Item -LiteralPath $old -Recurse -Force
        Write-Host "Removed $old"
    }
}

$itemDir = Join-Path $WorkshopDir $ItemId
if (-not (Test-Path -LiteralPath $itemDir -PathType Container)) {
    Write-Error ("Workshop item folder not found: $itemDir. Subscribe to item $ItemId " +
        "in Steam (https://steamcommunity.com/sharedfiles/filedetails/?id=$ItemId) and " +
        "let Steam download it first; the game loads zips only from subscribed item folders.")
    exit 1
}

$zipPath = Join-Path $itemDir 'Ellie-BrotatoBot.zip'
foreach ($other in Get-ChildItem -LiteralPath $itemDir -File -Filter '*.zip') {
    if ($other.FullName -ne $zipPath) {
        $disabled = "$($other.FullName).disabled"
        if (Test-Path -LiteralPath $disabled) { Remove-Item -LiteralPath $disabled -Force }
        Rename-Item -LiteralPath $other.FullName -NewName "$($other.Name).disabled"
        Write-Host "Disabled $($other.FullName) -> $disabled"
    }
}
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
