@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ========================================================
echo   Обновление файлов проекта с GitHub (без Git)
echo ========================================================
echo.

set PYTHON_CMD=py
py --version >nul 2>&1
if errorlevel 1 (
    set PYTHON_CMD=python
)

%PYTHON_CMD% -c "
import urllib.request, zipfile, io, shutil, os

url = 'https://github.com/Jokemachine/Change-pin-BasIpAERO/archive/refs/heads/arena/01a0cd2b-change-pin-basipaero.zip'
print('Скачивание обновлений с GitHub...')
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as resp:
    data = resp.read()

print('Распаковка файлов...')
with zipfile.ZipFile(io.BytesIO(data)) as z:
    # First dir inside zip is Change-pin-BasIpAERO-arena-...
    root_dir = z.namelist()[0]
    for member in z.namelist():
        if member.endswith('/'):
            continue
        rel_path = member[len(root_dir):]
        if not rel_path:
            continue
        target_path = os.path.join('.', rel_path)
        # Protect local config.yaml from being overwritten if it already exists
        if rel_path.lower() == 'config.yaml' and os.path.exists(target_path):
            print('Сохраняем ваш текущий config.yaml (не перезаписывается)')
            continue
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with z.open(member) as src, open(target_path, 'wb') as dst:
            shutil.copyfileobj(src, dst)

print('Файлы успешно обновлены!')
"

echo.
echo ========================================================
echo   Обновление завершено!
echo ========================================================
echo.
pause
