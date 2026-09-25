"""
Standalone GitHub updater for Change-pin-BasIpAERO.
Can be run via: py updater.py or update.bat
"""
import io
import os
import shutil
import sys
import urllib.error
import urllib.request
import zipfile

REPO_OWNER = "Jokemachine"
REPO_NAME = "Change-pin-BasIpAERO"
BRANCH = "arena/01a0cd2b-change-pin-basipaero"

# Possible token file names (Windows often appends .txt automatically)
CANDIDATE_TOKEN_FILES = [
    ".github_token",
    ".github_token.txt",
    "github_token.txt",
    "github_token",
    ".token",
    ".token.txt",
]

PROTECTED_LOCAL_FILES = {
    "config.yaml",
    ".github_token",
    ".github_token.txt",
    "github_token.txt",
    ".env",
    "service_account.json",
}


def find_saved_token() -> str:
    """Find token from environment or candidate token files."""
    env_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if env_token:
        return env_token.strip("\"'")

    for fname in CANDIDATE_TOKEN_FILES:
        if os.path.exists(fname):
            try:
                with open(fname, "r", encoding="utf-8") as f:
                    content = f.read().strip().strip("\"'")
                    if content:
                        print(f"Найден сохраненный токен в файле: {fname}")
                        return content
            except Exception:
                pass
    return ""


def download_repo_zip(token: str = "") -> bytes:
    """Download ZIP archive of the repository from GitHub (public or private)."""
    headers = {"User-Agent": "Mozilla/5.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/vnd.github+json"
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/zipball/{BRANCH}"
    else:
        url = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/{BRANCH}.zip"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def main():
    print("========================================================")
    print("  Обновление файлов проекта с GitHub")
    print(f"  Ветка: {BRANCH}")
    print("========================================================\n")

    token = find_saved_token()
    data = None

    print("Скачивание обновлений с GitHub...")
    try:
        data = download_repo_zip(token)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            print("\n[!] Репозиторий закрыт (приватный) или требуется авторизация GitHub.")
            print("    Для доступа нужен Personal Access Token (PAT).")
            print("    Создать токен: GitHub -> Settings -> Developer Settings -> Personal access tokens (classic) -> Generate new token (галочка repo).\n")
            try:
                entered = input("Введите ваш токен GitHub (ghp_...): ").strip().strip("\"'")
            except (KeyboardInterrupt, EOFError):
                print("\nОтменено пользователем.")
                return 1

            if not entered:
                print("Токен не введен. Обновление отменено.")
                return 1

            try:
                data = download_repo_zip(entered)
                with open(".github_token", "w", encoding="utf-8") as f:
                    f.write(entered)
                print("Токен успешно проверен и сохранен в .github_token для следующих обновлений.")
            except Exception as err2:
                print(f"\n[ОШИБКА] Не удалось скачать репозиторий с указанным токеном: {err2}")
                return 1
        else:
            print(f"\n[ОШИБКА] Ошибка загрузки с GitHub: {e}")
            return 1
    except Exception as e:
        print(f"\n[ОШИБКА] Ошибка подключения к GitHub: {e}")
        return 1

    if not data:
        print("[ОШИБКА] Получен пустой архив.")
        return 1

    print("Распаковка файлов...")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            namelist = z.namelist()
            if not namelist:
                print("[ОШИБКА] Архив пуст.")
                return 1

            root_dir = namelist[0].split("/")[0] + "/"
            updated_count = 0

            for member in namelist:
                if member.endswith("/"):
                    continue
                if member.startswith(root_dir):
                    rel_path = member[len(root_dir):]
                else:
                    rel_path = member

                if not rel_path:
                    continue

                target_path = os.path.normpath(os.path.join(".", rel_path))

                # Do not overwrite local protected files
                base_name = os.path.basename(target_path).lower()
                if (base_name in PROTECTED_LOCAL_FILES or rel_path.lower() in PROTECTED_LOCAL_FILES) and os.path.exists(target_path):
                    continue

                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                try:
                    with z.open(member) as src, open(target_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    updated_count += 1
                except Exception as ex:
                    print(f"Предупреждение: не удалось обновить {target_path}: {ex}")

        print(f"\nУСПЕХ! Проект успешно обновлен. Обновлено файлов: {updated_count}")
        if os.path.exists("config.yaml"):
            print("Ваш рабочий config.yaml сохранен без изменений.")
        return 0

    except Exception as e:
        print(f"\n[ОШИБКА] Ошибка при распаковке архива: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
