@echo off
setlocal
set ROOT=%~dp0..
cd /d "%ROOT%"

for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$c=Get-Content 'config\case.json' -Raw|ConvertFrom-Json; $c.case_id"`) do set CASEID=%%I
set JOB=%CASEID%_meshcheck
set WORK=%ROOT%\cases\%CASEID%\abaqus_meshcheck

where abaqus >nul 2>nul
if errorlevel 1 (
  echo ERROR: abaqus launcher not found in PATH.
  exit /b 2
)

if not exist "%WORK%\%JOB%.inp" (
  echo ERROR: input file not found: %WORK%\%JOB%.inp
  echo Run Python step 06 first.
  exit /b 2
)

cd /d "%WORK%"
abaqus job=%JOB% input=%JOB%.inp datacheck interactive
if errorlevel 1 exit /b %errorlevel%

echo ABAQUS DATACHECK COMMAND: COMPLETED
endlocal
