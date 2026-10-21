@echo off
REM ============================================================================
REM DevPilot One-Click Local Fallback Demo Runner (Windows)
REM ============================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo [DevPilot] Starting Local Fallback Demo Setup...

REM Check for virtual environment
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

REM Run the python demo runner
"%PYTHON_EXE%" scripts\run_local_demo.py %*

endlocal
