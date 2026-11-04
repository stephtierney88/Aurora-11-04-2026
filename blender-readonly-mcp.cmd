@echo off
setlocal
set "AURORA_ROOT=%~dp0."
set "AURORA_PYTHON=C:\Anaconda\envs\aurora\python.exe"
set "BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
if not exist "%AURORA_PYTHON%" set "AURORA_PYTHON=python"
"%AURORA_PYTHON%" "%~dp0blender_readonly_mcp_server.py" --root "%AURORA_ROOT%" --blender "%BLENDER_EXE%" --allowed-root "%AURORA_ROOT%" --allowed-root "C:\Program Files\Blender Foundation\Blender 5.2" %*
exit /b %ERRORLEVEL%
