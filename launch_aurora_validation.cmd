@echo off
setlocal
cd /d "%~dp0"
if defined AURORA_PYTHON (
  "%AURORA_PYTHON%" aurora_validation_console.py %*
) else (
  "C:\Anaconda\envs\aurora\python.exe" aurora_validation_console.py %*
)
exit /b %errorlevel%
