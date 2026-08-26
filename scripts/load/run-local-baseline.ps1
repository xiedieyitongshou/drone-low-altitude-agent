param(
    [string]$BaseUrl = "http://host.docker.internal:8000",
    [string]$RunId = "",
    [int]$Vus = 3,
    [int]$UserCount = 3,
    [string]$RampUp = "15s",
    [string]$Hold = "45s",
    [string]$RampDown = "10s",
    [string]$Password = "LoadTestAa12",
    [switch]$Smoke
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$scriptsDir = Join-Path $repoRoot "scripts\load"
$reportsDir = Join-Path $repoRoot "evals\reports\load"

New-Item -ItemType Directory -Force -Path $reportsDir | Out-Null

if ([string]::IsNullOrWhiteSpace($RunId)) {
    $RunId = Get-Date -Format "yyyyMMddHHmmss"
}

$scriptName = if ($Smoke) { "k6-smoke.js" } else { "k6-api.js" }
$summaryName = if ($Smoke) { "k6-smoke-summary.json" } else { "k6-local-baseline-summary.json" }

$dockerArgs = @(
    "run",
    "--rm",
    "-v", "${scriptsDir}:/scripts",
    "-v", "${reportsDir}:/reports",
    "-e", "BASE_URL=$BaseUrl",
    "-e", "RUN_ID=day155_local_$RunId",
    "-e", "LOAD_TEST_PASSWORD=$Password"
)

if (-not $Smoke) {
    $dockerArgs += @(
        "-e", "VUS=$Vus",
        "-e", "USER_COUNT=$UserCount",
        "-e", "RAMP_UP=$RampUp",
        "-e", "HOLD=$Hold",
        "-e", "RAMP_DOWN=$RampDown"
    )
}

$dockerArgs += @(
    "grafana/k6:latest",
    "run",
    "--summary-export", "/reports/$summaryName",
    "/scripts/$scriptName"
)

Write-Host "Running $scriptName against $BaseUrl"
Write-Host "Summary export: $reportsDir\$summaryName"
docker @dockerArgs
