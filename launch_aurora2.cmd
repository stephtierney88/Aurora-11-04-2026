@echo off
setlocal
cd /d "%~dp0"
if not defined AURORA_PYTHON if exist "%~dp0.venv\Scripts\python.exe" set "AURORA_PYTHON=%~dp0.venv\Scripts\python.exe"
if not defined AURORA_PYTHON if exist "C:\Anaconda\envs\aurora\python.exe" set "AURORA_PYTHON=C:\Anaconda\envs\aurora\python.exe"
if not defined AURORA_PYTHON for /f "delims=" %%P in ('where python 2^>nul') do if not defined AURORA_PYTHON set "AURORA_PYTHON=%%P"
if not exist "%AURORA_PYTHON%" (
  echo AURORA launcher error: "%AURORA_PYTHON%" not found.
  exit /b 1
)
set "PYTHONUNBUFFERED=1"
if /i "%~1"=="--preflight" (
  "%AURORA_PYTHON%" "%~dp0aurora_preflight.py" --json
  exit /b
)
"%AURORA_PYTHON%" "%~dp0aurora_preflight.py" --quiet
if errorlevel 1 exit /b %errorlevel%
"%AURORA_PYTHON%" "%~dp0aurora2.py" %*
exit /b %errorlevel%
