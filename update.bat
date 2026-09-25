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

%PYTHON_CMD% -c "
import urllib.request, urllib.error, zipfile, io, shutil, os, sys

repo_owner = 'Jokemachine'
repo_name = 'Change-pin-BasIpAERO'
branch = 'arena/01a0cd2b-change-pin-basipaero'

token_file = '.github_token'
token = os.environ.get('GITHUB_TOKEN', '').strip()

if not token and os.path.exists(token_file):
    try:
        with open(token_file, 'r', encoding='utf-8') as f:
            token = f.read().strip()
    except Exception:
        pass

def download_zip(tok=''):
    headers = {'User-Agent': 'Mozilla/5.0'}
    if tok:
        headers['Authorization'] = f'Bearer {tok}'
        headers['Accept'] = 'application/vnd.github.v3+json'
        url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/zipball/{branch}'
    else:
        url = f'https://github.com/{repo_owner}/{repo_name}/archive/refs/heads/{branch}.zip'
    
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return resp.read()

data = None
print('Скачивание обновлений с GitHub...')
try:
    data = download_zip(token)
except urllib.error.HTTPError as e:
    if e.code in (401, 403, 404):
        print('\n[!] Репозиторий закрыт (приватный) или требуется авторизация GitHub.')
        print('    Для доступа нужен Personal Access Token (PAT).')
        print('    Создать токен: GitHub -> Settings -> Developer Settings -> Personal access tokens (classic) -> Generate new token (галочка repo).\n')
        entered_token = input('Введите ваш токен GitHub: ').strip()
        if not entered_token:
            print('Обновление отменено.')
            sys.exit(1)
        try:
            data = download_zip(entered_token)
            with open(token_file, 'w', encoding='utf-8') as f:
                f.write(entered_token)
            print('Токен сохранен в файл .github_token для следующих обновлений.')
        except Exception as err2:
            print(f'Ошибка скачивания с указанным токеном: {err2}')
            sys.exit(1)
    else:
        print(f'Ошибка загрузки: {e}')
        sys.exit(1)
except Exception as e:
    print(f'Ошибка подключения к GitHub: {e}')
    sys.exit(1)

print('Распаковка файлов...')
with zipfile.ZipFile(io.BytesIO(data)) as z:
    root_dir = z.namelist()[0]
    updated_files = 0
    for member in z.namelist():
        if member.endswith('/'):
            continue
        rel_path = member[len(root_dir):]
        if not rel_path:
            continue
        target_path = os.path.join('.', rel_path)
        # Protect local config.yaml and .github_token from being overwritten
        if rel_path.lower() in ('config.yaml', '.github_token') and os.path.exists(target_path):
            continue
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with z.open(member) as src, open(target_path, 'wb') as dst:
            shutil.copyfileobj(src, dst)
        updated_files += 1

print(f'Файлы успешно обновлены! (обновлено файлов: {updated_files})')
if os.path.exists('config.yaml'):
    print('Ваш рабочий config.yaml сохранен без изменений.')
"

echo.
echo ========================================================
echo   Обновление завершено!
echo ========================================================
echo.
pause
