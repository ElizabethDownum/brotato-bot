<#
.SYNOPSIS
Packs mod\Ellie-BrotatoBot and installs the zip where the Steam build of
Brotato will load it: the owner's own hidden Workshop item folder.

.DESCRIPTION
The Steam build runs from Brotato.pck with the mod loader's "steam" profile
(steam_workshop_enabled = true). Brotato's fork of the loader then loads
zips only from Steam Workshop item folders whose id is in the player's
subscription list (Platform.get_subscribed_mods, i.e.
Steam.getSubscribedItems). It never reads <GameDir>\mods, cannot open an
unpacked res://mods-unpacked folder, and skips workshop folders that are
not subscribed. There is no CLI switch for any of this.

So the mod lives in the folder of a Workshop item the owner uploaded as a
hidden item (visible to the owner alone) and is subscribed to. Steam fills
that folder with the uploaded zip; this script overwrites it with a fresh
build so a change can be tested without re-uploading. Any other zip in the
folder is renamed to *.zip.disabled so only this build loads. Steam rewrites
the folder only when the Workshop item itself is updated, which is the
owner's own upload, so the two never fight. Uploading a new version is a
separate manual step with the game's GodotWorkshopUtility.exe (see
docs/runbook.md, Mod section 2).

Stale installs from earlier methods (<GameDir>\mods\Ellie-BrotatoBot.zip,
<GameDir>\mods-unpacked\{Pasha-AutoBattler,Ellie-BrotatoBot} and the fake
item folder 9999999999) are removed. Refuses to run while Brotato.exe is
running. -ItemId is the owner's hidden Workshop item, BrotatoBot (3825008026,
uploaded 2026-10-22).
#>
[CmdletBinding()]
param(
    [string]$GameDir = 'D:\SteamLibrary\steamapps\common\Brotato',
    [string]$WorkshopDir = 'D:\SteamLibrary\steamapps\workshop\content\1942280',
    [string]$ItemId = '3825008026'
)

$ErrorActionPreference = 'Stop'

if (Get-Process Brotato -ErrorAction SilentlyContinue) {
    Write-Error 'Brotato is running; quit the game before syncing the mod.'
    exit 1
}
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

$built = & (Join-Path $PSScriptRoot 'pack_mod.ps1') | Select-Object -Last 1
$zipPath = Join-Path $itemDir 'BrotatoBot.zip'
foreach ($other in Get-ChildItem -LiteralPath $itemDir -File -Filter '*.zip') {
    if ($other.FullName -ne $zipPath) {
        $disabled = "$($other.FullName).disabled"
        if (Test-Path -LiteralPath $disabled) { Remove-Item -LiteralPath $disabled -Force }
        Rename-Item -LiteralPath $other.FullName -NewName "$($other.Name).disabled"
        Write-Host "Disabled $($other.FullName) -> $disabled"
    }
}
Copy-Item -LiteralPath $built -Destination $zipPath -Force
Write-Host "Installed $zipPath"
