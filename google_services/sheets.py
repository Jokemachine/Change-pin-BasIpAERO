"""
Google Sheets and Table integrations:
- GoogleAppsScriptBackend (Recommended: 100% free, no Google Cloud Console required!)
- AppSheetBackend (AppSheet REST API)
- GoogleSheetsService (Google Cloud Service Account API)
- LocalCSVSheetsBackend (Local file / offline mode)
"""
import csv
import logging
import os
import re
import time
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
import requests

from basip.models import AccessCodeUser

logger = logging.getLogger(__name__)


def extract_house_entrance_from_text(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Intelligently extracts House (дом) and Entrance (подъезд) from freeform strings
    such as '50 (2 под., 4 этаж)', '3п 6эт. кв. 93', 'д. 2, 3 подъезд, кв 45'.
    """
    if not text:
        return None, None
    
    house, entrance = None, None

    # House pattern: дом 2, д. 2, корпус 3, корп. 1
    h_m = re.search(r'\b(?:дом|д\.|корпус|корп\.|здание|house)\s*(\d+)', text, re.IGNORECASE)
    if h_m:
        house = h_m.group(1)

    # Entrance pattern:
    # 1. '2 подъезд', '2под', '2 п.', '2п'
    e_m = re.search(r'(\d+)\s*(?:подъезд|под\b|п\b|\.п)', text, re.IGNORECASE)
    if not e_m:
        # 2. 'подъезд 2', 'под. 2'
        e_m = re.search(r'\b(?:подъезд|под)\.?\s*(\d+)', text, re.IGNORECASE)
    if not e_m:
        # 3. 'п. 2' (not followed by кв)
        e_m = re.search(r'\bп\.?\s*(\d+)(?!\s*кв)', text, re.IGNORECASE)
    
    if e_m:
        entrance = e_m.group(1)

    return house, entrance

# Standard header column aliases
COLUMN_ALIASES = {
    "user_id": ["id", "user_id", "userid", "ид", "номер"],
    "name": ["name", "fio", "full_name", "имя", "фио", "пользователь"],
    "email": ["email", "e-mail", "mail", "почта", "электронная почта"],
    "apartment": ["apartment", "flat", "room", "office", "apt", "квартира", "офис", "помещение"],
    "house": ["house", "building", "дом", "здание", "корпус", "д."],
    "entrance": ["entrance", "porch", "section", "подъезд", "секция", "парадная", "п."],
    "access_panels": ["access", "access_panels", "panels", "доступ", "доступ (панели)", "панели", "доступные панели"],
    "code": ["code", "pin", "access_code", "passcode", "код", "код доступа", "пин", "текущий код", "рабочий код"],
    "auto_rotate": ["auto_rotate", "autorotate", "rotate", "автосмена", "ротация", "автоматическая смена"],
    "last_rotated": ["last_rotated", "last_changed", "last_change", "дата смены", "дата последней смены", "последняя смена"],
    "interval_days": ["interval", "interval_days", "период", "период (дней)", "интервал", "интервал (дней)"],
    "status": ["status", "state", "статус", "состояние"],
}

DEFAULT_HEADERS = [
    "ID",
    "ФИО",
    "Email",
    "Дом",
    "Подъезд",
    "Квартира",
    "Доступ (панели)",
    "Рабочий код",
    "Автосмена",
    "Дата последней смены",
    "Интервал (дней)",
    "Статус",
]


class BaseSheetsBackend:
    """Interface for reading and writing user access code data."""
    def get_users(self) -> List[AccessCodeUser]:
        raise NotImplementedError

    def update_user_code(
        self,
        user: AccessCodeUser,
        new_code: str,
        rotation_time: Optional[datetime] = None,
        status: str = "Успешно обновлен",
    ) -> bool:
        raise NotImplementedError


class GoogleAppsScriptBackend(BaseSheetsBackend):
    """
    Google Apps Script (GAS) Web App integration.
    DOES NOT require Google Cloud Console!
    Works in any country, with any standard Google account.
    """

    def __init__(
        self,
        web_app_url: str,
        api_key: str = "",
        timeout: int = 45,
        worksheet_name: str = "Временные коды",
        max_retries: int = 3,
        retry_delay: int = 30,
    ):
        self.web_app_url = web_app_url.strip()
        self.api_key = api_key.strip()
        self.timeout = timeout
        self.worksheet_name = worksheet_name.strip() if worksheet_name else "Временные коды"
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        if not self.web_app_url:
            raise ValueError("Google Apps Script web_app_url cannot be empty")

    def get_users(self) -> List[AccessCodeUser]:
        """Fetch users from Google Apps Script Web App with automatic retries on timeout."""
        params = {"action": "get_users"}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.worksheet_name:
            params["sheet_name"] = self.worksheet_name

        logger.debug("Requesting users from Google Apps Script: %s (sheet=%s)", self.web_app_url, self.worksheet_name)
        resp = None

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.get(self.web_app_url, params=params, timeout=self.timeout, allow_redirects=True)
                if resp.status_code == 200:
                    break
                logger.warning(
                    "Google Apps Script вернул HTTP %d (попытка %d из %d). Ожидание %d сек...",
                    resp.status_code, attempt, self.max_retries, self.retry_delay,
                )
                time.sleep(self.retry_delay)
            except requests.exceptions.ConnectionError as e:
                err_str = str(e)
                if "getaddrinfo failed" in err_str or "NameResolutionError" in err_str:
                    raise RuntimeError(
                        "Ошибка подключения к Google (DNS [Errno 11002]): компьютер не может связаться с 'script.google.com'.\n"
                        "Возможные причины:\n"
                        "1. Компьютер подключен к локальной сети домофонов (172.39.x.x), где нет выхода в интернет.\n"
                        "2. Отсутствует подключение к интернету или сбой DNS-сервера.\n"
                        "3. Попробуйте выполнить в командной строке: ipconfig /flushdns"
                    ) from None
                if attempt < self.max_retries:
                    logger.warning(
                        "Google Apps Script ошибка подключения (%s). Повторная попытка через %d сек (попытка %d из %d)...",
                        e, self.retry_delay, attempt, self.max_retries,
                    )
                    time.sleep(self.retry_delay)
                    continue
                raise
            except requests.exceptions.Timeout as e:
                if attempt < self.max_retries:
                    logger.warning(
                        "Google Apps Script не ответил за %d сек (Read timed out). Повторная попытка через %d секунд (попытка %d из %d)...",
                        self.timeout, self.retry_delay, attempt, self.max_retries,
                    )
                    time.sleep(self.retry_delay)
                    continue
                raise
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries:
                    logger.warning(
                        "Ошибка запроса к Google Apps Script (%s). Повторная попытка через %d сек (попытка %d из %d)...",
                        e, self.retry_delay, attempt, self.max_retries,
                    )
                    time.sleep(self.retry_delay)
                    continue
                raise

        if resp is None or resp.status_code != 200:
            status_code = resp.status_code if resp is not None else 500
            err_text = resp.text if resp is not None else "No response"
            raise RuntimeError(f"Google Apps Script returned status {status_code}: {err_text}")

        data = resp.json()
        if not data.get("success", False) and "users" not in data:
            raise RuntimeError(f"Google Apps Script error: {data.get('error', 'Unknown error')}")

        accessed_sheet = data.get("sheet_name", self.worksheet_name)
        logger.info("Reading data from sheet tab: '%s'", accessed_sheet)

        raw_users = data.get("users", [])
        users: List[AccessCodeUser] = []

        for item in raw_users:
            name = str(item.get("name", "")).strip()
            email = str(item.get("email", "")).strip()
            if not name and not email:
                continue

            user_id = str(item.get("id", f"user_{item.get('row_index', 0)}"))
            apartment = str(item.get("apartment", "")).strip()
            house = str(item.get("house", item.get("building", ""))).strip()
            entrance = str(item.get("entrance", item.get("porch", ""))).strip()
            access_panels = str(item.get("access_panels", item.get("access", ""))).strip()

            # Fallback: extract house and entrance from apartment text if missing
            if apartment and (not house or not entrance):
                parsed_h, parsed_e = extract_house_entrance_from_text(apartment)
                if not house and parsed_h:
                    house = parsed_h
                if not entrance and parsed_e:
                    entrance = parsed_e
            code = str(item.get("code", "")).strip()
            auto_rotate_raw = str(item.get("auto_rotate", "Да")).lower()
            auto_rotate = auto_rotate_raw in ("да", "true", "1", "yes", "+")

            last_rotated_str = str(item.get("last_rotated", "")).strip()
            last_rotated = None
            if last_rotated_str:
                for fmt in (
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d %H:%M",
                    "%Y-%m-%d",
                    "%d.%m.%Y %H:%M:%S",
                    "%d.%m.%Y %H:%M",
                    "%d.%m.%Y",
                ):
                    try:
                        last_rotated = datetime.strptime(last_rotated_str, fmt)
                        break
                    except ValueError:
                        continue

            try:
                interval_days = int(item.get("interval_days", 14))
            except (ValueError, TypeError):
                interval_days = 14

            status = str(item.get("status", ""))

            users.append(
                AccessCodeUser(
                    row_index=int(item.get("row_index", 0)),
                    user_id=user_id,
                    name=name,
                    email=email,
                    apartment=apartment,
                    house=house,
                    entrance=entrance,
                    access_panels=access_panels,
                    current_code=code,
                    auto_rotate=auto_rotate,
                    last_rotated=last_rotated,
                    interval_days=interval_days,
                    status=status,
                )
            )

        logger.info("Successfully fetched %d users from Google Apps Script", len(users))
        return users

    def update_user_code(
        self,
        user: AccessCodeUser,
        new_code: str,
        rotation_time: Optional[datetime] = None,
        status: str = "Успешно обновлен",
    ) -> bool:
        """Update user's access code, date, and status in Google Sheet via Apps Script with retries."""
        if rotation_time is None:
            rotation_time = datetime.now()
        date_str = rotation_time.strftime("%Y-%m-%d %H:%M:%S")

        payload = {
            "action": "update_code",
            "sheet_name": self.worksheet_name,
            "user_id": user.user_id,
            "name": user.name,
            "email": user.email,
            "code": new_code,
            "status": status,
            "timestamp": date_str,
        }
        if self.api_key:
            payload["api_key"] = self.api_key

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(self.web_app_url, json=payload, timeout=self.timeout, allow_redirects=True)
                if resp.status_code != 200:
                    # Fallback to GET parameters if POST had redirect issue
                    resp = requests.get(self.web_app_url, params=payload, timeout=self.timeout, allow_redirects=True)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success", False):
                        user.current_code = new_code
                        user.last_rotated = rotation_time
                        user.status = status
                        logger.info("Updated Google Sheet for '%s': code=%s", user.name, new_code)
                        return True
                    raise RuntimeError(f"Apps Script update failed: {data.get('error')}")
                logger.warning(
                    "Google Apps Script update_code вернул HTTP %d (попытка %d из %d). Ожидание %d сек...",
                    resp.status_code, attempt, self.max_retries, self.retry_delay,
                )
                time.sleep(self.retry_delay)
            except requests.exceptions.ConnectionError as e:
                err_str = str(e)
                if "getaddrinfo failed" in err_str or "NameResolutionError" in err_str:
                    raise RuntimeError(
                        "Ошибка подключения к Google (DNS [Errno 11002]): нет связи с 'script.google.com'."
                    ) from None
                if attempt < self.max_retries:
                    logger.warning("Ошибка соединения при записи в Google Apps Script (%s). Повтор через %d сек...", e, self.retry_delay)
                    time.sleep(self.retry_delay)
                    continue
                raise
            except requests.exceptions.Timeout as e:
                if attempt < self.max_retries:
                    logger.warning(
                        "Google Apps Script не ответил за %d сек при сохранении кода. Повторная попытка через %d сек (попытка %d из %d)...",
                        self.timeout, self.retry_delay, attempt, self.max_retries,
                    )
                    time.sleep(self.retry_delay)
                    continue
                raise
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries:
                    logger.warning(
                        "Ошибка сети при сохранении в Google Apps Script (%s). Повторная попытка через %d сек...",
                        e, self.retry_delay,
                    )
                    time.sleep(self.retry_delay)
                    continue
                raise

        raise RuntimeError("Failed to update user code in Google Apps Script after retries")


class AppSheetBackend(BaseSheetsBackend):
    """
    AppSheet REST API integration (https://www.appsheet.com).
    Connects to Google Sheets through an AppSheet application.
    """

    def __init__(
        self,
        app_id: str,
        access_key: str,
        table_name: str = "Коды доступа",
        region: str = "www",  # "www" or "eu"
        timeout: int = 15,
    ):
        self.app_id = app_id.strip()
        self.access_key = access_key.strip()
        self.table_name = table_name.strip()
        self.base_url = f"https://{region}.appsheet.com/api/v2/apps/{self.app_id}/tables/{self.table_name}/Action"
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {
            "ApplicationAccessKey": self.access_key,
            "Content-Type": "application/json",
        }

    def get_users(self) -> List[AccessCodeUser]:
        """Fetch rows from AppSheet using 'Action': 'Find'."""
        body = {
            "Action": "Find",
            "Properties": {"Locale": "ru-RU"},
            "Rows": [],
        }
        resp = requests.post(self.base_url, headers=self._headers(), json=body, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"AppSheet API returned status {resp.status_code}: {resp.text}")

        rows = resp.json()
        if not isinstance(rows, list):
            rows = []

        users: List[AccessCodeUser] = []
        for idx, row in enumerate(rows, start=2):
            if not isinstance(row, dict):
                continue

            def get_val(key_aliases: List[str], default: str = "") -> str:
                for alias in key_aliases:
                    for k, v in row.items():
                        if k.strip().lower() == alias:
                            return str(v).strip()
                return default

            name = get_val(COLUMN_ALIASES["name"])
            email = get_val(COLUMN_ALIASES["email"])
            if not name and not email:
                continue

            user_id = get_val(COLUMN_ALIASES["user_id"], default=f"user_{idx}")
            apartment = get_val(COLUMN_ALIASES["apartment"])
            house = get_val(COLUMN_ALIASES["house"])
            entrance = get_val(COLUMN_ALIASES["entrance"])
            access_panels = get_val(COLUMN_ALIASES["access_panels"])
            code = get_val(COLUMN_ALIASES["code"])
            auto_rotate = get_val(COLUMN_ALIASES["auto_rotate"], default="да").lower() in ("да", "true", "1", "yes", "+")

            last_rotated_str = get_val(COLUMN_ALIASES["last_rotated"])
            last_rotated = None
            if last_rotated_str:
                for fmt in ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y"):
                    try:
                        last_rotated = datetime.strptime(last_rotated_str, fmt)
                        break
                    except ValueError:
                        continue

            try:
                interval_days = int(get_val(COLUMN_ALIASES["interval_days"], default="14"))
            except ValueError:
                interval_days = 14

            status = get_val(COLUMN_ALIASES["status"])

            users.append(
                AccessCodeUser(
                    row_index=idx,
                    user_id=user_id,
                    name=name,
                    email=email,
                    apartment=apartment,
                    house=house,
                    entrance=entrance,
                    access_panels=access_panels,
                    current_code=code,
                    auto_rotate=auto_rotate,
                    last_rotated=last_rotated,
                    interval_days=interval_days,
                    status=status,
                )
            )

        logger.info("Successfully fetched %d users from AppSheet", len(users))
        return users

    def update_user_code(
        self,
        user: AccessCodeUser,
        new_code: str,
        rotation_time: Optional[datetime] = None,
        status: str = "Успешно обновлен",
    ) -> bool:
        """Update code in AppSheet using 'Action': 'Edit'."""
        if rotation_time is None:
            rotation_time = datetime.now()
        date_str = rotation_time.strftime("%Y-%m-%d %H:%M:%S")

        body = {
            "Action": "Edit",
            "Properties": {"Locale": "ru-RU"},
            "Rows": [
                {
                    "ID": user.user_id,
                    "Рабочий код": new_code,
                    "Дата последней смены": date_str,
                    "Статус": status,
                }
            ],
        }
        resp = requests.post(self.base_url, headers=self._headers(), json=body, timeout=self.timeout)
        if resp.status_code == 200:
            user.current_code = new_code
            user.last_rotated = rotation_time
            user.status = status
            logger.info("Updated AppSheet for user '%s': new_code=%s", user.name, new_code)
            return True

        raise RuntimeError(f"AppSheet update failed: HTTP {resp.status_code} - {resp.text}")


class GoogleSheetsService(BaseSheetsBackend):
    """
    Google Sheets API backend using gspread and Service Account credentials.
    Requires Google Cloud Console.
    """

    def __init__(
        self,
        credentials_file: str,
        spreadsheet_id_or_title: str,
        worksheet_name: Optional[str] = None,
    ):
        self.credentials_file = credentials_file
        self.spreadsheet_id_or_title = spreadsheet_id_or_title
        self.worksheet_name = worksheet_name
        self._client = None
        self._spreadsheet = None
        self._worksheet = None
        self._col_map: Dict[str, int] = {}

    def _connect(self):
        if self._worksheet is not None:
            return

        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly",
        ]

        if not os.path.exists(self.credentials_file):
            raise FileNotFoundError(
                f"Google service account file not found: {self.credentials_file}. "
                "Please configure a valid credentials JSON file or use GoogleAppsScriptBackend."
            )

        creds = Credentials.from_service_account_file(self.credentials_file, scopes=scopes)
        self._client = gspread.authorize(creds)

        if "/" in self.spreadsheet_id_or_title or len(self.spreadsheet_id_or_title) > 30:
            key = self.spreadsheet_id_or_title
            if "/d/" in key:
                key = key.split("/d/")[1].split("/")[0]
            self._spreadsheet = self._client.open_by_key(key)
        else:
            try:
                self._spreadsheet = self._client.open_by_key(self.spreadsheet_id_or_title)
            except Exception:
                self._spreadsheet = self._client.open(self.spreadsheet_id_or_title)

        if self.worksheet_name:
            self._worksheet = self._spreadsheet.worksheet(self.worksheet_name)
        else:
            self._worksheet = self._spreadsheet.sheet1

        self._discover_columns()

    def _discover_columns(self):
        headers = self._worksheet.row_values(1)
        self._col_map.clear()
        for idx, h in enumerate(headers, start=1):
            normalized = h.strip().lower()
            for field_name, aliases in COLUMN_ALIASES.items():
                if normalized in aliases and field_name not in self._col_map:
                    self._col_map[field_name] = idx

    def get_users(self) -> List[AccessCodeUser]:
        self._connect()
        all_values = self._worksheet.get_all_values()
        if not all_values:
            return []

        self._discover_columns()
        users: List[AccessCodeUser] = []
        for row_idx, row in enumerate(all_values[1:], start=2):
            if not row or not any(row):
                continue

            def get_val(field_key: str, default: str = "") -> str:
                col_idx = self._col_map.get(field_key)
                if col_idx is not None and col_idx <= len(row):
                    return row[col_idx - 1].strip()
                return default

            name = get_val("name")
            email = get_val("email")
            if not name and not email:
                continue

            user_id = get_val("user_id", default=f"user_{row_idx}")
            apartment = get_val("apartment")
            house = get_val("house")
            entrance = get_val("entrance")
            access_panels = get_val("access_panels")
            code = get_val("code")
            auto_rotate = get_val("auto_rotate", "да").lower() in ("да", "true", "1", "yes", "+")

            last_rotated_str = get_val("last_rotated")
            last_rotated = None
            if last_rotated_str:
                for fmt in (
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d %H:%M",
                    "%Y-%m-%d",
                    "%d.%m.%Y %H:%M:%S",
                    "%d.%m.%Y",
                ):
                    try:
                        last_rotated = datetime.strptime(last_rotated_str, fmt)
                        break
                    except ValueError:
                        continue

            try:
                interval_days = int(get_val("interval_days", "14"))
            except ValueError:
                interval_days = 14

            status = get_val("status")

            users.append(
                AccessCodeUser(
                    row_index=row_idx,
                    user_id=user_id,
                    name=name,
                    email=email,
                    apartment=apartment,
                    house=house,
                    entrance=entrance,
                    access_panels=access_panels,
                    current_code=code,
                    auto_rotate=auto_rotate,
                    last_rotated=last_rotated,
                    interval_days=interval_days,
                    status=status,
                )
            )

        return users

    def update_user_code(
        self,
        user: AccessCodeUser,
        new_code: str,
        rotation_time: Optional[datetime] = None,
        status: str = "Успешно обновлен",
    ) -> bool:
        self._connect()
        if rotation_time is None:
            rotation_time = datetime.now()

        date_str = rotation_time.strftime("%Y-%m-%d %H:%M:%S")

        updates = []
        code_col = self._col_map.get("code")
        if code_col:
            updates.append({"range": f"{self._worksheet.title}!R{user.row_index}C{code_col}", "values": [[new_code]]})

        date_col = self._col_map.get("last_rotated")
        if date_col:
            updates.append({"range": f"{self._worksheet.title}!R{user.row_index}C{date_col}", "values": [[date_str]]})

        status_col = self._col_map.get("status")
        if status_col:
            updates.append({"range": f"{self._worksheet.title}!R{user.row_index}C{status_col}", "values": [[status]]})

        if updates:
            self._worksheet.batch_update(updates)

        user.current_code = new_code
        user.last_rotated = rotation_time
        user.status = status
        return True


class LocalCSVSheetsBackend(BaseSheetsBackend):
    """
    Local CSV file backend for offline operation, testing, and backups.
    """

    def __init__(self, filepath: str = "users_access_codes.csv"):
        self.filepath = filepath
        self._col_map: Dict[str, int] = {}
        if not os.path.exists(self.filepath) or os.path.getsize(self.filepath) == 0:
            self._create_sample_file()

    def _create_sample_file(self):
        with open(self.filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(DEFAULT_HEADERS)
            writer.writerow([
                "101",
                "Иванов Иван Иванович",
                "ivanov@example.com",
                "1",          # Дом 1
                "1",          # Подъезд 1 (двойной: внешняя + внутренняя дверь)
                "12",         # Квартира
                "Дом 1 Подъезд 1", # Доступ: автоматически добавит 2 калитки + 2 двери подъезда 1
                "123456",
                "Да",
                "2026-09-01 10:00:00",
                "14",
                "Активен",
            ])
            writer.writerow([
                "102",
                "Петрова Анна Сергеевна",
                "petrova@example.com",
                "2",          # Дом 2
                "4",          # Подъезд 4
                "105",        # Квартира
                "Дом 2 Подъезд 4",
                "654321",
                "Да",
                "2026-09-20 12:00:00",
                "14",
                "Активен",
            ])
            writer.writerow([
                "103",
                "Сидоров Петр",
                "sidorov@example.com",
                "3",          # Дом 3
                "2",          # Подъезд 2
                "45",         # Квартира
                "Дом 3 Подъезд 2",
                "789012",
                "Нет",
                "2026-08-01 09:00:00",
                "14",
                "Постоянный код",
            ])
            writer.writerow([
                "104",
                "Служба Охраны / Сервис",
                "security@example.com",
                "Все",        # Все дома
                "Все",        # Все подъезды
                "Охрана",
                "Все",        # Доступ ко всем 38 панелям
                "991122",
                "Да",
                "2026-09-05 08:00:00",
                "14",
                "Активен",
            ])

    def get_users(self) -> List[AccessCodeUser]:
        if not os.path.exists(self.filepath):
            return []

        users = []
        with open(self.filepath, "r", newline="", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            if not reader:
                return []

            headers = reader[0]
            self._col_map.clear()
            for idx, h in enumerate(headers):
                normalized = h.strip().lower()
                for field_name, aliases in COLUMN_ALIASES.items():
                    if normalized in aliases and field_name not in self._col_map:
                        self._col_map[field_name] = idx

            for row_idx, row in enumerate(reader[1:], start=2):
                if not row or not any(row):
                    continue

                def get_val(key: str, default: str = "") -> str:
                    col = self._col_map.get(key)
                    if col is not None and col < len(row):
                        return row[col].strip()
                    return default

                name = get_val("name")
                email = get_val("email")
                if not name and not email:
                    continue

                user_id = get_val("user_id", f"user_{row_idx}")
                apartment = get_val("apartment")
                house = get_val("house")
                entrance = get_val("entrance")
                access_panels = get_val("access_panels")

                if apartment and (not house or not entrance):
                    parsed_h, parsed_e = extract_house_entrance_from_text(apartment)
                    if not house and parsed_h:
                        house = parsed_h
                    if not entrance and parsed_e:
                        entrance = parsed_e
                code = get_val("code")
                auto_rotate = get_val("auto_rotate", "да").lower() in ("да", "true", "1", "yes", "+")

                last_rotated_str = get_val("last_rotated")
                last_rotated = None
                if last_rotated_str:
                    for fmt in (
                        "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%d %H:%M",
                        "%Y-%m-%d",
                        "%d.%m.%Y %H:%M:%S",
                        "%d.%m.%Y",
                    ):
                        try:
                            last_rotated = datetime.strptime(last_rotated_str, fmt)
                            break
                        except ValueError:
                            continue

                try:
                    interval_days = int(get_val("interval_days", "14"))
                except ValueError:
                    interval_days = 14

                status = get_val("status")

                users.append(
                    AccessCodeUser(
                        row_index=row_idx,
                        user_id=user_id,
                        name=name,
                        email=email,
                        apartment=apartment,
                        house=house,
                        entrance=entrance,
                        access_panels=access_panels,
                        current_code=code,
                        auto_rotate=auto_rotate,
                        last_rotated=last_rotated,
                        interval_days=interval_days,
                        status=status,
                    )
                )

        return users

    def update_user_code(
        self,
        user: AccessCodeUser,
        new_code: str,
        rotation_time: Optional[datetime] = None,
        status: str = "Успешно обновлен",
    ) -> bool:
        if rotation_time is None:
            rotation_time = datetime.now()
        date_str = rotation_time.strftime("%Y-%m-%d %H:%M:%S")

        with open(self.filepath, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        target_row_idx = user.row_index - 1
        if target_row_idx < len(rows):
            code_col = self._col_map.get("code")
            date_col = self._col_map.get("last_rotated")
            status_col = self._col_map.get("status")

            if code_col is not None and code_col < len(rows[target_row_idx]):
                rows[target_row_idx][code_col] = new_code
            if date_col is not None and date_col < len(rows[target_row_idx]):
                rows[target_row_idx][date_col] = date_str
            if status_col is not None and status_col < len(rows[target_row_idx]):
                rows[target_row_idx][status_col] = status

            with open(self.filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerows(rows)

            user.current_code = new_code
            user.last_rotated = rotation_time
            user.status = status
            return True

        return False
