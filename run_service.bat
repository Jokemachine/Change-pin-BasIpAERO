@echo off
chcp 65001 > nul
cd /d "%~dp0"

set PYTHON_EXEC=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXEC=.venv\Scripts\python.exe
    goto :run
)
py --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_EXEC=py
    goto :run
)

:run
%PYTHON_EXEC% main.py daemon
pause
