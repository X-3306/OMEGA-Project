@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON_EXE=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo The virtual environment was not found at "%PYTHON_EXE%".
    echo Create it first with: python -m venv .venv
    exit /b 1
)
"%PYTHON_EXE%" "%ROOT%OMEGA_BETA.py"
