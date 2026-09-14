$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "[1/4] Build periodic topology"
python .\01_build_periodic_topology.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[2/4] Extract master boundary curves"
python .\02_extract_master_boundaries.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[3/4] Standardize master boundary curves"
python .\03_standardize_master_boundaries.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[4/4] Export CGAL input"
python .\04_export_cgal_input.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "PREPROCESS PIPELINE: PASS"
