$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
python .\07_validate_abaqus_datacheck.py
exit $LASTEXITCODE
