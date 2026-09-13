@echo off
setlocal
set ROOT=%~dp0..
cd /d "%ROOT%"

where cl >nul 2>nul
if errorlevel 1 (
  echo ERROR: cl.exe was not found.
  echo Open "x64 Native Tools Command Prompt for VS" first, then activate diffumeta_cgal.
  exit /b 2
)

where cmake >nul 2>nul
if errorlevel 1 (
  echo ERROR: cmake was not found. Activate the diffumeta_cgal environment.
  exit /b 2
)

if exist cgal_mesher\build rmdir /s /q cgal_mesher\build
cmake -S cgal_mesher -B cgal_mesher\build -G Ninja -DCMAKE_BUILD_TYPE=Release
if errorlevel 1 exit /b %errorlevel%

cmake --build cgal_mesher\build
if errorlevel 1 exit /b %errorlevel%

echo CGAL BUILD: PASS
endlocal
