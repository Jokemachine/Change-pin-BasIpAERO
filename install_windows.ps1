# PowerShell установщик для BAS-IP PIN Rotator
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "BAS-IP PIN Rotator - Установка"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Установка и настройка BAS-IP PIN Rotator на Windows" -ForegroundColor Cyan
Write-Host "========================================================`n" -ForegroundColor Cyan

# 1. Поиск Python
$pythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py -3"
}

if (-not $pythonCmd) {
    Write-Host "[ОШИБКА] Python не найден в системе Windows!" -ForegroundColor Red
    Write-Host "Для работы требуется Python 3.10 или новее." -ForegroundColor Yellow
    Write-Host "Скачайте его с https://www.python.org/downloads/ и ОБЯЗАТЕЛЬНО отметьте галочку 'Add python.exe to PATH'.`n"
    $ans = Read-Host "Открыть страницу скачивания в браузере? (Y/N)"
    if ($ans -eq "Y" -or $ans -eq "y") {
        Start-Process "https://www.python.org/downloads/"
    }
    Read-Host "Нажмите Enter для выхода..."
    exit 1
}

Write-Host "[1/3] Найден Python:" -ForegroundColor Green
Invoke-Expression "$pythonCmd --version"
Write-Host ""

# 2. Создание venv
Write-Host "[2/3] Создание виртуального окружения (.venv)..." -ForegroundColor Green
if (-not (Test-Path ".venv")) {
    Invoke-Expression "$pythonCmd -m venv .venv"
    Write-Host "Окружение .venv создано.`n" -ForegroundColor Gray
} else {
    Write-Host "Окружение .venv уже существует.`n" -ForegroundColor Gray
}

# 3. Установка requirements.txt
Write-Host "[3/3] Установка библиотек..." -ForegroundColor Green
$pipExe = ".venv\Scripts\pip.exe"
if (Test-Path $pipExe) {
    & $pipExe install --upgrade pip
    & $pipExe install -r requirements.txt
} else {
    Invoke-Expression "$pythonCmd -m pip install --upgrade pip"
    Invoke-Expression "$pythonCmd -m pip install -r requirements.txt"
}

Write-Host "`n========================================================" -ForegroundColor Green
Write-Host "  УСТАНОВКА УСПЕШНО ЗАВЕРШЕНА!" -ForegroundColor Green
Write-Host "========================================================`n" -ForegroundColor Green
Write-Host "Теперь вы можете запускать:"
Write-Host " - list_panels.bat  - список всех 38 панелей"
Write-Host " - test_sheets.bat  - проверка Google Таблицы"
Write-Host " - run_dry_run.bat  - тестовая симуляция"
Write-Host " - run_now.bat      - боевой запуск`n"

Read-Host "Нажмите Enter для завершения..."
