@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo   Установка и настройка BAS-IP PIN Rotator на Windows
echo ========================================================
echo.

set PYTHON_CMD=

py -3 --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=py -3
    goto :python_found
)

py --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=py
    goto :python_found
)

python --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=python
    goto :python_found
)

goto :python_not_found

:python_found
echo [1/3] Найден Python:
%PYTHON_CMD% --version
echo.

echo [2/3] Создание виртуального окружения (.venv)...
if not exist ".venv" (
    %PYTHON_CMD% -m venv .venv
    echo Виртуальное окружение .venv успешно создано.
) else (
    echo Виртуальное окружение .venv уже существует.
)
echo.

echo [3/3] Установка библиотек...
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\pip.exe install requests pyyaml schedule python-dotenv
    .venv\Scripts\pip.exe install -r requirements.txt
) else (
    %PYTHON_CMD% -m pip install --upgrade pip
    %PYTHON_CMD% -m pip install requests pyyaml schedule python-dotenv
    %PYTHON_CMD% -m pip install -r requirements.txt
)

echo.
echo ========================================================
echo   УСТАНОВКА УСПЕШНО ЗАВЕРШЕНА!
echo ========================================================
echo.
echo Теперь вы можете запускать:
echo  - list_panels.bat  - список всех 38 панелей
echo  - test_sheets.bat  - проверка подключения к Google Таблице
echo  - run_dry_run.bat  - тестовая симуляция ротации кодов
echo  - run_now.bat      - боевой запуск смены кодов
echo.
pause
exit /b 0

:python_not_found
echo.
echo ========================================================
echo   ОШИБКА: Python не найден в системе Windows!
echo ========================================================
echo.
echo Для работы программы требуется Python 3.10 или новее.
echo.
echo Что нужно сделать:
echo 1. Если Python 3.14 уже установлен:
echo    Отключите псевдонимы Windows Store:
echo    Параметры Windows -> Приложения -> Псевдонимы выполнения приложений
echo    -> отключите галочки у "Установщик приложений (python.exe)".
echo 2. Либо запустите установщик Python еще раз и выберите Modify,
echo    отметив галочку "Add python.exe to PATH".
echo.
echo Открыть страницу скачивания Python в браузере? (Y/N)
set /p OPEN_BROWSER="Введите Y или N: "
if /i "%OPEN_BROWSER%"=="Y" start https://www.python.org/downloads/
echo.
pause
exit /b 1
