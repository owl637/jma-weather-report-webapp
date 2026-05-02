param(
    [string]$TaskPrefix = "JMA-Overview",
    [string]$UserName = $env:USERNAME
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$runner = Join-Path $repoRoot "scripts\run_overview_job.ps1"

if (-not (Test-Path $runner)) {
    throw "Runner script not found: $runner"
}

$taskSpecs = @(
    @{ Name = "$TaskPrefix-05"; Time = "05:05"; Slot = "05" },
    @{ Name = "$TaskPrefix-11"; Time = "11:05"; Slot = "11" },
    @{ Name = "$TaskPrefix-17"; Time = "17:05"; Slot = "17" }
)

foreach ($spec in $taskSpecs) {
    $taskName = $spec.Name
    $time = $spec.Time
    $slot = $spec.Slot

    $taskCommand = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$runner`" -Slot $slot"

    schtasks /Create /F /SC DAILY /TN $taskName /TR $taskCommand /ST $time /RL LIMITED /RU $UserName | Out-Null
    Write-Host "[OK] Registered task: $taskName at $time"
}
