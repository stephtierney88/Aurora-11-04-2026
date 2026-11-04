@echo off
setlocal
cd /d "%~dp0"
if not defined AURORA_PYTHON set "AURORA_PYTHON=C:\Anaconda\envs\aurora\python.exe"
if not exist "%AURORA_PYTHON%" (
  echo Aurora CLI error: "%AURORA_PYTHON%" not found.
  exit /b 1
)
"%AURORA_PYTHON%" "%~dp0aurora_cli.py" %*
set "AURORA_EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %AURORA_EXIT_CODE%
