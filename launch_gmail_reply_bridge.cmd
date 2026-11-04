@echo off
setlocal
cd /d "%~dp0"
set "AURORA_PYTHON=C:\Anaconda\envs\aurora\python.exe"
if not exist "%AURORA_PYTHON%" set "AURORA_PYTHON=python.exe"
if not defined AURORA_GMAIL_APP_PASSWORD (
  for /f "usebackq delims=" %%I in (`powershell.exe -NoProfile -Command "[Environment]::GetEnvironmentVariable('AURORA_GMAIL_APP_PASSWORD','User')"` ) do set "AURORA_GMAIL_APP_PASSWORD=%%I"
)
"%AURORA_PYTHON%" "%~dp0gmail_reply_bridge.py" %*
endlocal
