# =============================================================================
# Aethelburg v0.3.0-beta.1 — Quick Launcher (Windows PowerShell)
# =============================================================================
param(
    [switch]$BootstrapOnly,
    [int]$Port = 8050
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  AETHELBURG v0.3.0-beta.1 — Corporate Intelligence (FtM)   " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Use the project's virtual environment when it exists (it has every dependency)
$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
    Write-Host "No .venv found: using the system Python. Create one with:" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv; .venv\Scripts\python.exe -m pip install -e ." -ForegroundColor Yellow
}

if ($BootstrapOnly) {
    & $Python -m src.main data status --offline
    & $Python -m src.main stats
    exit 0
}

Write-Host "Starting Aethelburg on http://127.0.0.1:$Port ..." -ForegroundColor Green
Write-Host "First time? Open the '6. Data & Updates' tab to download and import the data." -ForegroundColor Green
& $Python -m src.main desktop --port $Port
