@echo off
setlocal
cd /d "%~dp0"
if not defined AURORA_PYTHON if exist "%~dp0.venv\Scripts\python.exe" set "AURORA_PYTHON=%~dp0.venv\Scripts\python.exe"
if not defined AURORA_PYTHON if exist "C:\Anaconda\envs\aurora\python.exe" set "AURORA_PYTHON=C:\Anaconda\envs\aurora\python.exe"
if not defined AURORA_PYTHON for /f "delims=" %%P in ('where python 2^>nul') do if not defined AURORA_PYTHON set "AURORA_PYTHON=%%P"
if not exist "%AURORA_PYTHON%" (
  echo AURORA control-panel launcher error: no Aurora Python runtime found.
  exit /b 1
)
set "AURORA_PREFLIGHT_PYTHON=%AURORA_PYTHON:pythonw.exe=python.exe%"
if /i "%~1"=="--preflight" (
  "%AURORA_PREFLIGHT_PYTHON%" "%~dp0aurora_preflight.py" --surface panel --json
  exit /b
)
"%AURORA_PREFLIGHT_PYTHON%" "%~dp0aurora_preflight.py" --surface panel --quiet
if errorlevel 1 exit /b %errorlevel%
if exist "%AURORA_PYTHON:python.exe=pythonw.exe%" (
  start "" "%AURORA_PYTHON:python.exe=pythonw.exe%" "%~dp0aurora2_control_panel.py" %*
  exit /b 0
)
"%AURORA_PYTHON%" "%~dp0aurora2_control_panel.py" %*
exit /b %errorlevel%
