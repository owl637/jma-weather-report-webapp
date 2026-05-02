param(
    [string]$TaskPrefix = "JMA-Overview"
)

$ErrorActionPreference = "Stop"

$taskNames = @(
    "$TaskPrefix-05",
    "$TaskPrefix-11",
    "$TaskPrefix-17"
)

foreach ($taskName in $taskNames) {
    schtasks /Delete /F /TN $taskName | Out-Null
    Write-Host "[OK] Removed task: $taskName"
}
