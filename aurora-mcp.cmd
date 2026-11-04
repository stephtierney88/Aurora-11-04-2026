@echo off
setlocal
set "AURORA_ROOT=%~dp0."
set "AURORA_PYTHON=C:\Anaconda\envs\aurora\python.exe"
if not exist "%AURORA_PYTHON%" set "AURORA_PYTHON=python"
"%AURORA_PYTHON%" "%~dp0aurora_mcp_server.py" --root "%AURORA_ROOT%" %*
exit /b %ERRORLEVEL%
