@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ========================================================
echo   Обновление файлов проекта с GitHub
echo ========================================================
echo.

set PYTHON_CMD=py
py --version >nul 2>&1
if errorlevel 1 (
    set PYTHON_CMD=python
)

if not exist updater.py (
    echo [!] Файл updater.py не найден, запускаем первичное скачивание...
    %PYTHON_CMD% -c "import urllib.request, zipfile, io, os; tok = ''; ([setattr(tok, 'v', open(f, encoding='utf-8').read().strip().strip('\'\"')) for f in ('.github_token', '.github_token.txt', 'github_token.txt') if os.path.exists(f)] if hasattr(tok, 'v') else None); tok = getattr(tok, 'v', ''); h = {'User-Agent': 'Mozilla/5.0'}; (h.update({'Authorization': 'Bearer ' + tok, 'Accept': 'application/vnd.github+json'}) if tok else None); url = 'https://api.github.com/repos/Jokemachine/Change-pin-BasIpAERO/zipball/arena/01a0cd2b-change-pin-basipaero' if tok else 'https://github.com/Jokemachine/Change-pin-BasIpAERO/archive/refs/heads/arena/01a0cd2b-change-pin-basipaero.zip'; req = urllib.request.Request(url, headers=h); data = urllib.request.urlopen(req).read(); z = zipfile.ZipFile(io.BytesIO(data)); r = z.namelist()[0].split('/')[0] + '/'; [open(m[len(r):], 'wb').write(z.read(m)) for m in z.namelist() if not m.endswith('/') and not (m[len(r):].lower() == 'config.yaml' and os.path.exists(m[len(r):])) and os.makedirs(os.path.dirname(m[len(r):]) or '.', exist_ok=True) is None]; print('Файлы успешно загружены!')"
)

%PYTHON_CMD% updater.py
echo.
pause
