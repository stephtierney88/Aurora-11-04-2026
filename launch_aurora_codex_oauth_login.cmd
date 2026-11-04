@echo off
setlocal
cd /d "%~dp0"
set "AURORA_PYTHON=C:\Anaconda\envs\aurora\python.exe"
if not exist "%AURORA_PYTHON%" set "AURORA_PYTHON=python.exe"
"%AURORA_PYTHON%" "%~dp0aurora_codex_oauth.py" %*
endlocal
