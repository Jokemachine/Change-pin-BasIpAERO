@echo off
chcp 65001 > nul
echo ========================================================
echo   Установка и настройка BAS-IP PIN Rotator на Windows
echo ========================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден в системе!
    echo Пожалуйста, установите Python 3.10 или новее с официального сайта:
    echo https://www.python.org/downloads/
    echo ВАЖНО: При установке обязательно поставьте галочку "Add Python to PATH"!
    echo.
    pause
    exit /b 1
)

echo [1/3] Проверка версии Python...
python --version

echo.
echo [2/3] Создание виртуального окружения (.venv)...
if not exist ".venv" (
    python -m venv .venv
    echo Виртуальное окружение создано.
) else (
    echo Виртуальное окружение уже существует.
)

echo.
echo [3/3] Установка необходимых библиотек...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo ========================================================
echo   Установка успешно завершена!
echo ========================================================
echo.
echo Теперь вы можете запускать:
echo - list_panels.bat  - просмотр всех 38 панелей
echo - run_dry_run.bat  - проверка без внесения изменений
echo - run_now.bat      - боевой разовый запуск
echo - run_service.bat  - запуск непрерывной службы
echo.
pause
