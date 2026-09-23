"""
Topology and inventory of BAS-IP AA-14FB entrance panels:
4 houses + 2 gates, total 38 panels:
- House 1: 3 double entrances (6 panels)
- House 2: 6 double entrances (12 panels)
- House 3: 6 double entrances (12 panels)
- House 4: 3 double entrances (6 panels)
- 2 Gates (2 panels)
"""
from typing import List, Dict, Any, Optional
from basip.models import BASIPPanelConfig


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
            # Double entrance has 2 doors/panels:
            # Door A (Внешняя дверь / Дверь 1)
            # Door B (Внутренняя дверь / Дверь 2)
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
