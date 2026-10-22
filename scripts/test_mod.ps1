# Runs every res://mod/tests/test_*.gd headlessly under Godot 3.6.
# Exits with the runner's code: 0 when all tests pass, 1 otherwise
# (also 1 if Godot printed any SCRIPT ERROR).
#
# The Godot exe is a GUI-subsystem binary, so `& $exe` neither waits for it
# nor sets $LASTEXITCODE. Start-Process -Wait does both; stdout/stderr are
# redirected to temp files and echoed so the output is capturable.
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$exePath  = Join-Path $repoRoot 'tools\godot\Godot_v3.6-stable_win64.exe'

if (-not (Test-Path -LiteralPath $exePath)) {
    Write-Error "Godot not found at $exePath. Run scripts\get_godot.ps1 first."
    exit 2
}

$outFile = [System.IO.Path]::GetTempFileName()
$errFile = [System.IO.Path]::GetTempFileName()
try {
    $proc = Start-Process -FilePath $exePath `
        -ArgumentList @('--path', '.', '--no-window', '--script', 'mod/tests/run_tests.gd') `
        -WorkingDirectory $repoRoot -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $outFile -RedirectStandardError $errFile
    $out = @(Get-Content -LiteralPath $outFile)
    $err = @(Get-Content -LiteralPath $errFile)
    $out | Write-Output
    $err | ForEach-Object { [Console]::Error.WriteLine($_) }
    $code = $proc.ExitCode

    # Godot 3 cannot catch runtime errors inside a test method: the call
    # aborts, a SCRIPT ERROR goes to stderr, and the method may report PASS.
    # Treat any SCRIPT ERROR as a failure.
    $scriptErrors = @(($out + $err) | Select-String -SimpleMatch 'SCRIPT ERROR' -Context 0, 1)
    if ($scriptErrors.Count -gt 0) {
        Write-Output "FAIL $($scriptErrors.Count) SCRIPT ERROR(s) during the run:"
        $scriptErrors | ForEach-Object { Write-Output "  $($_.Line)"; $_.Context.PostContext | ForEach-Object { Write-Output "  $_" } }
        if ($code -eq 0) { $code = 1 }
    }
} finally {
    Remove-Item -LiteralPath $outFile, $errFile -Force -ErrorAction SilentlyContinue
}
exit $code
