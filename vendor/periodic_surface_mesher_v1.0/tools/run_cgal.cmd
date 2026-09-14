@echo off
setlocal
set ROOT=%~dp0..
cd /d "%ROOT%"

for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$c=Get-Content 'config\case.json' -Raw|ConvertFrom-Json; $c.case_id"`) do set CASEID=%%I

set EXE=%ROOT%\cgal_mesher\build\periodic_surface_mesher.exe
set CFG=%ROOT%\cases\%CASEID%\cgal_input\cgal_case.txt
set FEAT=%ROOT%\cases\%CASEID%\cgal_input\periodic3_master_features.txt
set OUT=%ROOT%\cases\%CASEID%\cgal_output\%CASEID%_mesh

if not exist "%EXE%" (
  echo ERROR: CGAL executable not found: %EXE%
  echo Run tools\build_cgal.cmd first.
  exit /b 2
)
if not exist "%CFG%" (
  echo ERROR: CGAL runtime config not found: %CFG%
  echo Run Python steps 01-04 first.
  exit /b 2
)

"%EXE%" "%CFG%" "%FEAT%" "%OUT%"
if errorlevel 1 exit /b %errorlevel%

echo CGAL MESH GENERATION: PASS
endlocal
