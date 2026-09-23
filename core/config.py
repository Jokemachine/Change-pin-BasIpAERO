"""
Configuration manager for BAS-IP PIN Rotator.
Loads parameters from YAML, .env files, or environment variables.
"""
import os
import yaml
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

from basip.models import BASIPPanelConfig
from basip.topology import generate_default_38_panels

load_dotenv()


@dataclass
class RotationConfig:
    interval_days: int = 14       # Default 2 weeks (14 days)
    code_length: int = 6          # Length of PIN code (4-8 digits)
    avoid_trivial_codes: bool = True
    dry_run: bool = False
    schedule_time: str = "03:00"  # Time of day for daily check (HH:MM)
    check_interval_hours: int = 12


@dataclass
class GoogleSheetsConfig:
    backend_type: str = "google_apps_script"  # "google_apps_script" (No GCP required!), "appsheet", "google_sheets", or "local_csv"
    
    # Settings for Google Apps Script (Recommended: free, works anywhere)
    gas_web_app_url: str = ""
    gas_api_key: str = ""

    # Settings for AppSheet REST API (https://www.appsheet.com)
    appsheet_app_id: str = ""
    appsheet_access_key: str = ""
    appsheet_table_name: str = "Коды доступа"

    # Settings for Google Cloud Service Account
    credentials_json: str = "service_account.json"
    spreadsheet_id_or_title: str = "BAS-IP Access Codes"
    worksheet_name: Optional[str] = "Коды доступа"
    csv_fallback_path: str = "users_access_codes.csv"


@dataclass
class GmailConfig:
    user: str = ""
    app_password: str = ""
    from_name: str = "Домофон BAS-IP AA-14FB"
    subject: str = "Смена кода доступа домофона"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    use_ssl: bool = True
    mock_email: bool = False  # Set to True to log instead of sending real email


@dataclass
class AppConfig:
    panels: List[BASIPPanelConfig] = field(default_factory=list)
    sheets: GoogleSheetsConfig = field(default_factory=GoogleSheetsConfig)
    gmail: GmailConfig = field(default_factory=GmailConfig)
    rotation: RotationConfig = field(default_factory=RotationConfig)
    use_mock_panel: bool = False
    mock_panel_port: int = 18080


def load_config(config_path: str = "config.yaml") -> AppConfig:
    """Load configuration from YAML file with environment variable overrides."""
    yaml_data: Dict[str, Any] = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}

    # 1. Panels config
    panels_list = []
    yaml_panels = yaml_data.get("basip_panels", [])
    topo_config = yaml_data.get("facility_topology", {})
    use_38_panels = topo_config.get("use_default_38_panels", True) if topo_config else ("facility_topology" in yaml_data or not yaml_panels)

    if use_38_panels and not yaml_panels:
        # Auto-generate 38 panels (4 houses with double entrances + 2 gates)
        prefix = topo_config.get("base_ip_prefix", os.getenv("BASIP_IP_PREFIX", "192.168.1."))
        start_suffix = int(topo_config.get("start_ip_suffix", os.getenv("BASIP_START_IP_SUFFIX", 10)))
        port = int(topo_config.get("default_port", os.getenv("BASIP_PORT", 80)))
        user = topo_config.get("default_username", os.getenv("BASIP_USER", "admin"))
        pwd = topo_config.get("default_password", os.getenv("BASIP_PASSWORD", "123456"))

        panels_list = generate_default_38_panels(
            base_ip_prefix=prefix,
            start_ip_suffix=start_suffix,
            default_port=port,
            default_username=user,
            default_password=pwd,
        )
    elif isinstance(yaml_panels, list) and yaml_panels:
        for p in yaml_panels:
            panels_list.append(
                BASIPPanelConfig(
                    panel_id=str(p.get("panel_id", f"panel_{len(panels_list)+1}")),
                    name=str(p.get("name", "BAS-IP AA-14FB")),
                    building=p.get("building"),
                    entrance=p.get("entrance"),
                    door=p.get("door"),
                    is_gate=bool(p.get("is_gate", False)),
                    enabled=bool(p.get("enabled", True)),
                    host=p.get("host", "192.168.1.100"),
                    port=int(p.get("port", 80)),
                    username=p.get("username", "admin"),
                    password=p.get("password", "123456"),
                    use_https=bool(p.get("use_https", False)),
                    api_version=p.get("api_version", "v1"),
                    lock_number=int(p.get("lock_number", 1)),
                    auth_mode=p.get("auth_mode", "token"),
                    timeout=int(p.get("timeout", 8)),
                )
            )
    else:
        # Default single panel from env or defaults
        host = os.getenv("BASIP_HOST", "192.168.1.100")
        port = int(os.getenv("BASIP_PORT", "80"))
        username = os.getenv("BASIP_USER", "admin")
        password = os.getenv("BASIP_PASSWORD", "123456")
        use_https = os.getenv("BASIP_USE_HTTPS", "false").lower() in ("true", "1")
        panels_list.append(
            BASIPPanelConfig(
                panel_id="panel_1",
                name="Входная панель",
                host=host,
                port=port,
                username=username,
                password=password,
                use_https=use_https,
            )
        )

    # 2. Sheets config
    yaml_sheets = yaml_data.get("google_sheets", {})
    sheets_backend = os.getenv("SHEETS_BACKEND", yaml_sheets.get("backend_type", "google_apps_script"))
    gas_url = os.getenv("GAS_WEB_APP_URL", yaml_sheets.get("gas_web_app_url", ""))
    gas_key = os.getenv("GAS_API_KEY", yaml_sheets.get("gas_api_key", ""))
    appsheet_id = os.getenv("APPSHEET_APP_ID", yaml_sheets.get("appsheet_app_id", ""))
    appsheet_key = os.getenv("APPSHEET_ACCESS_KEY", yaml_sheets.get("appsheet_access_key", ""))
    appsheet_table = os.getenv("APPSHEET_TABLE_NAME", yaml_sheets.get("appsheet_table_name", "Коды доступа"))
    sheets_creds = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", yaml_sheets.get("credentials_json", "service_account.json"))
    sheets_id = os.getenv("GOOGLE_SPREADSHEET_ID", yaml_sheets.get("spreadsheet_id_or_title", "BAS-IP Access Codes"))
    sheets_ws = os.getenv("GOOGLE_WORKSHEET_NAME", yaml_sheets.get("worksheet_name", "Коды доступа"))
    csv_path = os.getenv("CSV_FALLBACK_PATH", yaml_sheets.get("csv_fallback_path", "users_access_codes.csv"))

    sheets_config = GoogleSheetsConfig(
        backend_type=sheets_backend,
        gas_web_app_url=gas_url,
        gas_api_key=gas_key,
        appsheet_app_id=appsheet_id,
        appsheet_access_key=appsheet_key,
        appsheet_table_name=appsheet_table,
        credentials_json=sheets_creds,
        spreadsheet_id_or_title=sheets_id,
        worksheet_name=sheets_ws,
        csv_fallback_path=csv_path,
    )

    # 3. Gmail config
    yaml_gmail = yaml_data.get("gmail", {})
    gmail_user = os.getenv("GMAIL_USER", yaml_gmail.get("user", ""))
    gmail_pwd = os.getenv("GMAIL_APP_PASSWORD", yaml_gmail.get("app_password", ""))
    gmail_from = os.getenv("GMAIL_FROM_NAME", yaml_gmail.get("from_name", "Домофон BAS-IP AA-14FB"))
    gmail_subject = os.getenv("GMAIL_SUBJECT", yaml_gmail.get("subject", "Смена кода доступа домофона"))
    mock_email = os.getenv("GMAIL_MOCK", str(yaml_gmail.get("mock_email", False))).lower() in ("true", "1")

    gmail_config = GmailConfig(
        user=gmail_user,
        app_password=gmail_pwd,
        from_name=gmail_from,
        subject=gmail_subject,
        smtp_host=yaml_gmail.get("smtp_host", "smtp.gmail.com"),
        smtp_port=int(yaml_gmail.get("smtp_port", 465)),
        use_ssl=bool(yaml_gmail.get("use_ssl", True)),
        mock_email=mock_email,
    )

    # 4. Rotation config
    yaml_rot = yaml_data.get("rotation", {})
    rot_interval = int(os.getenv("ROTATION_INTERVAL_DAYS", yaml_rot.get("interval_days", 14)))
    rot_len = int(os.getenv("PIN_CODE_LENGTH", yaml_rot.get("code_length", 6)))
    dry_run = os.getenv("DRY_RUN", str(yaml_rot.get("dry_run", False))).lower() in ("true", "1")
    use_mock_panel = os.getenv("USE_MOCK_PANEL", str(yaml_data.get("use_mock_panel", False))).lower() in ("true", "1")

    rotation_config = RotationConfig(
        interval_days=rot_interval,
        code_length=rot_len,
        avoid_trivial_codes=bool(yaml_rot.get("avoid_trivial_codes", True)),
        dry_run=dry_run,
        schedule_time=yaml_rot.get("schedule_time", "03:00"),
        check_interval_hours=int(yaml_rot.get("check_interval_hours", 12)),
    )

    return AppConfig(
        panels=panels_list,
        sheets=sheets_config,
        gmail=gmail_config,
        rotation=rotation_config,
        use_mock_panel=use_mock_panel,
        mock_panel_port=int(yaml_data.get("mock_panel_port", 18080)),
    )
