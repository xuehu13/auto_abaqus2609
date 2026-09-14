@echo off
if not defined PIXI_VSDEVCMD exit /b 2
call "%PIXI_VSDEVCMD%" -no_logo -arch=x64 -host_arch=x64 >nul
if errorlevel 1 exit /b %errorlevel%
set
