@echo off
setlocal
cd /d "%~dp0"
if not defined AURORA_PYTHON set "AURORA_PYTHON=C:\Anaconda\envs\aurora\python.exe"
if not exist "%AURORA_PYTHON%" (
  echo OBS read-only adapter error: Python interpreter not found. 1>&2
  exit /b 1
)
"%AURORA_PYTHON%" "%~dp0obs_readonly_mcp_server.py" --root "%~dp0." %*
set "AURORA_EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %AURORA_EXIT_CODE%
