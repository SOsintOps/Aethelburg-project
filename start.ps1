# =============================================================================
# Aethelburg v0.2.0-beta.1 — Quick Launcher (Windows PowerShell)
# =============================================================================
param(
    [switch]$BootstrapOnly,
    [int]$Port = 8050
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  AETHELBURG v0.2.0-beta.1 — Corporate Intelligence (FtM)   " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if (-not (Test-Path "dati\aethelburg.sqlite")) {
    Write-Host "[1/2] Initializing FollowTheMoney database from dati/..." -ForegroundColor Yellow
    python -m src.main bootstrap
}

if ($BootstrapOnly) {
    python -m src.main stats
    exit 0
}

Write-Host "[2/2] Starting Aethelburg Web & Desktop UI on http://127.0.0.1:$Port ..." -ForegroundColor Green
python -m src.main desktop --port $Port
