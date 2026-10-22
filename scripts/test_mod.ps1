# Runs every res://mod/tests/test_*.gd headlessly under Godot 3.6.
# Exits 0 only when Godot exits 0, prints an "N passed, 0 failed" summary,
# and prints no SCRIPT ERROR. Otherwise exits 1 (2 if Godot is missing).
#
# The Godot exe is a GUI-subsystem binary, so `& $exe` neither waits for it
# nor sets $LASTEXITCODE. Start-Process plus WaitForExit does both and allows
# a timeout; stdout/stderr are redirected to temp files and echoed.
param(
    [int]$TimeoutSeconds = 120
)
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$exePath  = Join-Path $repoRoot 'tools\godot\Godot_v3.6-stable_win64.exe'
$runner   = 'mod/tests/run_tests.gd'

if (-not (Test-Path -LiteralPath $exePath)) {
    Write-Error "Godot not found at $exePath. Run scripts\get_godot.ps1 first."
    exit 2
}

$outFile = [System.IO.Path]::GetTempFileName()
$errFile = [System.IO.Path]::GetTempFileName()
$code = 1
try {
    $proc = Start-Process -FilePath $exePath `
        -ArgumentList @('--path', '.', '--no-window', '--script', $runner) `
        -WorkingDirectory $repoRoot -NoNewWindow -PassThru `
        -RedirectStandardOutput $outFile -RedirectStandardError $errFile
    # Touch Handle so ExitCode stays readable after the process exits.
    $null = $proc.Handle

    $timedOut = -not $proc.WaitForExit($TimeoutSeconds * 1000)
    if ($timedOut) {
        try { $proc.Kill() } catch { }
        $proc.WaitForExit(5000) | Out-Null
    } else {
        $proc.WaitForExit()  # flush redirected output
    }

    $out = @(Get-Content -LiteralPath $outFile)
    $err = @(Get-Content -LiteralPath $errFile)
    $out | Write-Output
    $err | ForEach-Object { [Console]::Error.WriteLine($_) }

    $exitCode = $proc.ExitCode
    $summary = $out | Where-Object { $_ -match '^\d+ passed, \d+ failed$' } | Select-Object -Last 1
    $runnerFailed = $summary -and ($summary -notmatch ' 0 failed$')

    # Wrapper diagnostics for anything the runner did not report itself.
    $problems = @()
    if ($timedOut) {
        $problems += "FAIL timed out after $TimeoutSeconds s; Godot was killed"
    } elseif ($null -eq $exitCode -or $exitCode -isnot [int]) {
        $problems += "FAIL Godot exit code unavailable ('$exitCode')"
    } elseif ($exitCode -ne 0 -and -not ($exitCode -eq 1 -and $runnerFailed)) {
        $problems += "FAIL Godot exited with code $exitCode"
    }

    # Exit 0 alone is not proof the runner ran: require its summary line.
    if (-not $summary) {
        $problems += "FAIL no '<N> passed, <M> failed' summary from $runner"
    }

    # Godot 3 cannot catch runtime errors inside a test method: the call
    # aborts, a SCRIPT ERROR goes to stderr, and the method may report PASS.
    $scriptErrors = @(($out + $err) | Select-String -SimpleMatch 'SCRIPT ERROR' -Context 0, 1)
    if ($scriptErrors.Count -gt 0) {
        $problems += "FAIL $($scriptErrors.Count) SCRIPT ERROR(s) during the run:"
        $scriptErrors | ForEach-Object {
            $problems += "  $($_.Line)"
            $_.Context.PostContext | ForEach-Object { $problems += "  $_" }
        }
    }

    $problems | Write-Output
    if ($problems.Count -eq 0 -and $summary -match '^\d+ passed, 0 failed$') {
        $code = 0
    }
} finally {
    Remove-Item -LiteralPath $outFile, $errFile -Force -ErrorAction SilentlyContinue
}
exit $code
