@echo off
setlocal
set "AURORA_ROOT=%~dp0."
set "AURORA_PYTHON=C:\Anaconda\envs\aurora\python.exe"
set "FL_STUDIO_EXE=C:\Program Files\Image-Line\FL Studio 2025\FL64.exe"
if not exist "%AURORA_PYTHON%" set "AURORA_PYTHON=python"
"%AURORA_PYTHON%" "%~dp0fl_studio_readonly_mcp_server.py" --root "%AURORA_ROOT%" --fl "%FL_STUDIO_EXE%" %*
exit /b %ERRORLEVEL%
