"""
Data models for BAS-IP AA-14FB and user access management.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class BASIPPanelConfig:
    """Configuration for connecting to a single BAS-IP AA-14FB panel."""
    panel_id: str = "panel_1"
    name: str = "BAS-IP AA-14FB"
    building: Optional[int] = None   # House number: 1, 2, 3, 4 (or None for gates)
    entrance: Optional[int] = None   # Entrance number: 1..6 (or None for gates)
    door: Optional[str] = None       # Door: "A", "B", "1", "2"
    is_gate: bool = False            # True for communal gates/wickets (калитки)
    enabled: bool = True             # Allow temporarily disabling a panel

    host: str = "192.168.1.100"
    port: int = 80
    username: str = "admin"
    password: str = "123456"
    use_https: bool = False
    api_version: str = "v1"  # "v1" or "v0"
    lock_number: int = 1     # 0: all locks, 1: first lock, 2: second lock
    auth_mode: str = "token" # "token" (Bearer token via MD5 login) or "basic"
    timeout: int = 8

    @property
    def base_url(self) -> str:
        protocol = "https" if self.use_https else "http"
        return f"{protocol}://{self.host}:{self.port}/api/{self.api_version}"

    @property
    def location_str(self) -> str:
        if self.is_gate:
            return f"Калитка ({self.name})"
        b_str = f"Дом {self.building}" if self.building else ""
        e_str = f"Подъезд {self.entrance}" if self.entrance else ""
        d_str = f"Дверь {self.door}" if self.door else ""
        parts = [p for p in (b_str, e_str, d_str) if p]
        return ", ".join(parts) if parts else self.name


@dataclass
class AccessCodeUser:
    """Represents a user whose access code is managed and rotated."""
    row_index: int
    user_id: str
    name: str
    email: str
    apartment: str = ""
    house: str = ""                  # e.g. "1", "2", "3", "4", "Все"
    entrance: str = ""               # e.g. "1", "2", "Все"
    access_panels: str = ""          # Custom filter e.g. "Дом 1 Подъезд 2", "Все"
    current_code: str = ""
    auto_rotate: bool = True
    last_rotated: Optional[datetime] = None
    interval_days: int = 14
    status: str = ""

    def is_due_for_rotation(self, now: Optional[datetime] = None) -> bool:
        """Check if user's access code is due for rotation (e.g. every 14 days)."""
        if not self.auto_rotate:
            return False
        if not self.current_code:
            return True
        if self.last_rotated is None:
            return True
        if now is None:
            now = datetime.now()
        days_passed = (now - self.last_rotated).total_seconds() / 86400.0
        return days_passed >= self.interval_days

    def can_access_panel(self, panel: BASIPPanelConfig) -> bool:
        """
        Determine if this user has access to a specific panel.
        Rules:
        1. Gates (is_gate=True) are ALWAYS accessible to all users.
        2. If access_panels / house / entrance contains 'все' / 'all' / '*', access is granted.
        3. Matches user's assigned house and entrance.
        4. Matches explicit panel IDs or names if specified in access_panels.
        """
        if not panel.enabled:
            return False

        # 1. Gates are accessible to everyone (User requirement: "калитки естественно будут всегда использоваться и доступ будет у всех")
        if panel.is_gate:
            return True

        # Check explicit 'all' override
        all_markers = ("все", "all", "*", "любой", "любые")
        if (
            self.house.strip().lower() in all_markers
            or self.entrance.strip().lower() in all_markers
            or self.access_panels.strip().lower() in all_markers
        ):
            return True

        # Check custom access_panels string (e.g. "gate_1, d1_p2_a" or "Дом 1 Подъезд 2")
        if self.access_panels:
            raw = self.access_panels.lower()
            if panel.panel_id.lower() in raw:
                return True
            if panel.name.lower() in raw:
                return True
            # Check pattern like "дом 1" or "д. 1"
            if panel.building and f"дом {panel.building}" in raw:
                # If entrance is also mentioned in raw string
                if panel.entrance and f"подъезд {panel.entrance}" in raw:
                    return True
                if "подъезд" not in raw:
                    # Access to entire house
                    return True

        # Match by House and Entrance
        if self.house:
            # Parse possible comma-separated houses e.g. "1, 2" or "1"
            clean_house = self.house.lower().replace("дом", "").replace("д.", "").strip()
            user_houses = [h.strip() for h in clean_house.split(",") if h.strip()]
            panel_house = str(panel.building) if panel.building is not None else ""
            if panel_house not in user_houses:
                return False

            # If entrance is specified, check entrance
            if self.entrance:
                clean_entrance = self.entrance.lower().replace("подъезд", "").replace("п.", "").strip()
                user_entrances = [e.strip() for e in clean_entrance.split(",") if e.strip()]
                if any(ue in all_markers for ue in user_entrances):
                    return True
                panel_entrance = str(panel.entrance) if panel.entrance is not None else ""
                if panel_entrance not in user_entrances:
                    return False

            return True

        return False


@dataclass
class Identifier:
    """Identifier representation in BAS-IP AA-14FB."""
    identifier_number: str
    identifier_type: str = "input_code"
    name: str = ""
    item_uid: Optional[int] = None
    link_id: Optional[int] = None
    lock_number: int = 1
    apartment_number: Optional[str] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)
