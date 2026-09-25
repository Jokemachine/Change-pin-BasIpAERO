@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ========================================================
echo   Обновление файлов проекта с GitHub
echo ========================================================
echo.

set PYTHON_CMD=py
py --version >nul 2>&1
if errorlevel 1 set PYTHON_CMD=python

%PYTHON_CMD% updater.py
echo.
pause
