"""
Topology and inventory of BAS-IP AA-14FB entrance panels:
4 houses + 2 gates, total 38 panels:
- House 1: 3 double entrances (6 panels)
- House 2: 6 double entrances (12 panels)
- House 3: 6 double entrances (12 panels)
- House 4: 3 double entrances (6 panels)
- 2 Gates (2 panels)
"""
import csv
import logging
import os
import yaml
from typing import List, Dict, Any, Optional
from basip.models import BASIPPanelConfig

logger = logging.getLogger(__name__)


def generate_default_38_panels(
    base_ip_prefix: str = "192.168.1.",
    start_ip_suffix: int = 10,
    default_port: int = 80,
    default_username: str = "admin",
    default_password: str = "123456",
) -> List[BASIPPanelConfig]:
    """
    Generates the complete 38-panel topology according to the facility layout:
    - 2 Gates (калитки): accessible to ALL residents
    - House 1: 3 double entrances (6 panels)
    - House 2: 6 double entrances (12 panels)
    - House 3: 6 double entrances (12 panels)
    - House 4: 3 double entrances (6 panels)
    """
    panels: List[BASIPPanelConfig] = []
    current_ip_suffix = start_ip_suffix

    # 1. Gates (Калитки) - 2 panels
    gate_names = [
        ("gate_1", "Калитка 1 (Северная/Главная)"),
        ("gate_2", "Калитка 2 (Южная/Въезд)"),
    ]
    for p_id, p_name in gate_names:
        panels.append(
            BASIPPanelConfig(
                panel_id=p_id,
                name=p_name,
                building=None,
                entrance=None,
                door=None,
                is_gate=True,
                host=f"{base_ip_prefix}{current_ip_suffix}",
                port=default_port,
                username=default_username,
                password=default_password,
            )
        )
        current_ip_suffix += 1

    # Houses configuration: (house_number, entrance_count)
    houses_spec = [
        (1, 3),   # House 1: 3 double entrances = 6 panels
        (2, 6),   # House 2: 6 double entrances = 12 panels
        (3, 6),   # House 3: 6 double entrances = 12 panels
        (4, 3),   # House 4: 3 double entrances = 6 panels
    ]

    for house_num, entrance_count in houses_spec:
        for ent in range(1, entrance_count + 1):
            doors = [
                ("A", "Внешняя"),
                ("B", "Внутренняя"),
            ]
            for door_code, door_desc in doors:
                panel_id = f"d{house_num}_p{ent}_{door_code.lower()}"
                panel_name = f"Дом {house_num}, Подъезд {ent} ({door_desc})"
                panels.append(
                    BASIPPanelConfig(
                        panel_id=panel_id,
                        name=panel_name,
                        building=house_num,
                        entrance=ent,
                        door=door_code,
                        is_gate=False,
                        host=f"{base_ip_prefix}{current_ip_suffix}",
                        port=default_port,
                        username=default_username,
                        password=default_password,
                    )
                )
                current_ip_suffix += 1

    return panels


def load_panels_from_yaml(filepath: str) -> List[BASIPPanelConfig]:
    """Load panels list from a standalone YAML file (panels.yaml)."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Panels YAML file not found: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []

    panels: List[BASIPPanelConfig] = []
    for p in data:
        panels.append(
            BASIPPanelConfig(
                panel_id=str(p.get("panel_id", f"panel_{len(panels)+1}")),
                name=str(p.get("name", "BAS-IP AA-14FB")),
                building=p.get("building"),
                entrance=p.get("entrance"),
                door=p.get("door"),
                is_gate=bool(p.get("is_gate", False)),
                enabled=bool(p.get("enabled", True)),
                host=str(p.get("host", "192.168.1.100")),
                port=int(p.get("port", 80)),
                username=str(p.get("username", "admin")),
                password=str(p.get("password", "123456")),
                use_https=bool(p.get("use_https", False)),
                api_version=str(p.get("api_version", "v1")),
                lock_number=int(p.get("lock_number", 1)),
                auth_mode=str(p.get("auth_mode", "token")),
                timeout=int(p.get("timeout", 8)),
            )
        )
    return panels


def load_panels_from_csv(filepath: str) -> List[BASIPPanelConfig]:
    """Load panels list from a CSV file (panels.csv) - convenient for Excel editing."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Panels CSV file not found: {filepath}")

    panels: List[BASIPPanelConfig] = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row.get("ID") or row.get("panel_id", f"panel_{len(panels)+1}")
            name = row.get("Название") or row.get("name", "BAS-IP AA-14FB")
            b_val = row.get("Дом") or row.get("building")
            e_val = row.get("Подъезд") or row.get("entrance")
            d_val = row.get("Дверь") or row.get("door")
            is_gate_val = str(row.get("Калитка") or row.get("is_gate", "")).lower()
            is_gate = is_gate_val in ("да", "true", "1", "yes", "+")

            host = row.get("IP") or row.get("host", "192.168.1.100")
            port = int(row.get("Порт") or row.get("port", 80))
            user = row.get("Логин") or row.get("username", "admin")
            pwd = row.get("Пароль") or row.get("password", "123456")

            panels.append(
                BASIPPanelConfig(
                    panel_id=str(pid).strip(),
                    name=str(name).strip(),
                    building=int(b_val) if b_val and str(b_val).isdigit() else None,
                    entrance=int(e_val) if e_val and str(e_val).isdigit() else None,
                    door=str(d_val).strip() if d_val else None,
                    is_gate=is_gate,
                    host=str(host).strip(),
                    port=port,
                    username=str(user).strip(),
                    password=str(pwd).strip(),
                )
            )
    return panels


def save_panels_to_csv(panels: List[BASIPPanelConfig], filepath: str):
    """Save panels list to CSV so user can open and edit in Excel."""
    headers = ["ID", "Название", "Дом", "Подъезд", "Дверь", "Калитка", "IP", "Порт", "Логин", "Пароль"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for p in panels:
            writer.writerow([
                p.panel_id,
                p.name,
                p.building or "",
                p.entrance or "",
                p.door or "",
                "Да" if p.is_gate else "Нет",
                p.host,
                p.port,
                p.username,
                p.password,
            ])
