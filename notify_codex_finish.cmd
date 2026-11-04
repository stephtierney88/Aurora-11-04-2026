@echo off
setlocal
cd /d "%~dp0"
set "AURORA_PYTHON=C:\Anaconda\envs\aurora\python.exe"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0notify_codex_finish.ps1" %*
endlocal
