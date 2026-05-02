param(
    [ValidateSet("05", "11", "17")]
    [string]$Slot = "17"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repoRoot

$logDir = Join-Path $repoRoot "logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$logFile = Join-Path $logDir "overview-collector.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

"[$timestamp] START slot=$Slot" | Out-File -FilePath $logFile -Encoding utf8 -Append

python fetch_overview_to_mongo.py --slot $Slot 2>&1 | Out-File -FilePath $logFile -Encoding utf8 -Append

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$timestamp] END slot=$Slot" | Out-File -FilePath $logFile -Encoding utf8 -Append
