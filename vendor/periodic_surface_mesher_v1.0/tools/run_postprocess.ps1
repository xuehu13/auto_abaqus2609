$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "[1/2] Validate final canonical shell"
python .\05_validate_shell.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[2/2] Export Abaqus S3R mesh-check input"
python .\06_export_abaqus_meshcheck.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "POSTPROCESS PIPELINE: PASS"
