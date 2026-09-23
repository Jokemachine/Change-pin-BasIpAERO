"""
BAS-IP AA-14FB Intercom API Client.
Handles local authentication, identifier retrieval, creation, updating, and deletion.
"""
import hashlib
import logging
from typing import List, Optional, Dict, Any
import requests
from requests.auth import HTTPBasicAuth

import concurrent.futures
from basip.models import BASIPPanelConfig, Identifier, AccessCodeUser

logger = logging.getLogger(__name__)


class BASIPError(Exception):
    """Base exception for BAS-IP API errors."""
    pass


class BASIPAuthError(BASIPError):
    """Authentication failure on BAS-IP panel."""
    pass


class BASIPClient:
    """Client for communicating with a BAS-IP AA-14FB door entrance panel."""

    def __init__(self, config: BASIPPanelConfig, session: Optional[requests.Session] = None):
        self.config = config
        self.session = session or requests.Session()
        self.token: Optional[str] = None
        self._authenticated = False

    def _get_password_hash(self) -> str:
        """BAS-IP uses uppercase MD5 hex digest for login."""
        return hashlib.md5(self.config.password.encode("utf-8")).hexdigest().upper()

    def login(self) -> bool:
        """
        Authenticate with the BAS-IP panel.
        Supports token-based auth (default) and Basic Auth.
        """
        if self.config.auth_mode == "basic":
            self.session.auth = HTTPBasicAuth(self.config.username, self.config.password)
            self._authenticated = True
            logger.info("Using HTTP Basic Auth for panel %s:%s", self.config.host, self.config.port)
            return True

        # Token-based authentication
        # BAS-IP panels support GET /api/v1/login or /api/v0/login with username and uppercase MD5 password
        url_candidates = [
            f"{self.config.base_url}/login",
            f"http{'s' if self.config.use_https else ''}://{self.config.host}:{self.config.port}/api/login",
            f"http{'s' if self.config.use_https else ''}://{self.config.host}:{self.config.port}/login",
        ]

        md5_pwd = self._get_password_hash()
        params = {
            "username": self.config.username,
            "password": md5_pwd,
        }

        last_error = None
        for login_url in url_candidates:
            try:
                logger.debug("Attempting BAS-IP login at %s", login_url)
                response = self.session.get(login_url, params=params, timeout=self.config.timeout)
                if response.status_code == 200:
                    data = response.json()
                    # Some firmware versions return {"token": "..."}
                    if isinstance(data, dict) and "token" in data:
                        self.token = data["token"]
                        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
                    elif isinstance(data, dict) and "data" in data and "token" in data["data"]:
                        self.token = data["data"]["token"]
                        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
                    self._authenticated = True
                    logger.info("Successfully authenticated on BAS-IP panel %s:%s", self.config.host, self.config.port)
                    return True
                elif response.status_code in (401, 403):
                    # Also try plain text password in case firmware uses plaintext POST/GET
                    logger.debug("MD5 login rejected with %s, trying plaintext login...", response.status_code)
                    plain_resp = self.session.post(
                        login_url,
                        json={"login": self.config.username, "password": self.config.password},
                        timeout=self.config.timeout
                    )
                    if plain_resp.status_code == 200:
                        data = plain_resp.json()
                        if isinstance(data, dict) and "token" in data:
                            self.token = data["token"]
                            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
                        self._authenticated = True
                        logger.info("Successfully authenticated on BAS-IP panel via POST %s", login_url)
                        return True
            except requests.RequestException as e:
                last_error = e
                continue

        # Fallback to HTTP Basic Auth if token endpoint not answering
        logger.warning(
            "Token login endpoints did not succeed (%s). Falling back to HTTP Basic Auth.",
            last_error or "Unexpected status",
        )
        self.session.auth = HTTPBasicAuth(self.config.username, self.config.password)
        self._authenticated = True
        return True

    def _request(self, method: str, path: str, retry_auth: bool = True, **kwargs) -> requests.Response:
        """Make an authenticated request with automatic re-login on 401."""
        if not self._authenticated:
            self.login()

        url = f"{self.config.base_url}{path}"
        if "timeout" not in kwargs:
            kwargs["timeout"] = self.config.timeout

        try:
            response = self.session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            logger.error("Network error connecting to BAS-IP at %s: %s", url, exc)
            raise BASIPError(f"Connection to BAS-IP panel {self.config.host} failed: {exc}") from exc

        if response.status_code == 401 and retry_auth:
            logger.warning("BAS-IP token expired or unauthorized (401), re-authenticating...")
            self._authenticated = False
            self.login()
            return self._request(method, path, retry_auth=False, **kwargs)

        return response

    def check_connection(self, return_detail: bool = False):
        """Verify panel availability and authorization."""
        try:
            self.login()
            resp = self._request("GET", "/access/identifier/items", params={"items_limit": 1})
            if resp.status_code in (200, 204):
                return (True, "Доступна и авторизована") if return_detail else True
            msg = f"Ошибка HTTP {resp.status_code}: {resp.text[:120]}"
            return (False, msg) if return_detail else False
        except Exception as e:
            err_msg = str(e)
            if "timed out" in err_msg.lower():
                msg = "Таймаут подключения (панель недоступна по сети)"
            elif "connection refused" in err_msg.lower():
                msg = "Соединение отклонено (порт закрыт или панель перезагружается)"
            elif "no route to host" in err_msg.lower() or "10051" in err_msg or "10065" in err_msg:
                msg = "Нет сетевого маршрута к IP (компьютер не в подсети 172.39.x.x)"
            else:
                msg = err_msg
            return (False, msg) if return_detail else False

    def get_identifiers(self, page: int = 1, limit: int = 100) -> List[Identifier]:
        """Fetch list of identifiers stored on the panel."""
        params = {"current_page": page, "items_limit": limit}
        resp = self._request("GET", "/access/identifier/items", params=params)
        if resp.status_code != 200:
            raise BASIPError(f"Failed to fetch identifiers: HTTP {resp.status_code} - {resp.text}")

        data = resp.json()
        raw_items = []
        if isinstance(data, dict):
            raw_items = data.get("list_items", []) or data.get("items", []) or data.get("data", [])
        elif isinstance(data, list):
            raw_items = data

        identifiers: List[Identifier] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            item_uid = item.get("item_uid") or item.get("id") or item.get("uid")
            link_id = item.get("link_id")
            num = str(item.get("identifier_number", item.get("code", item.get("number", ""))))
            id_type = item.get("identifier_type", item.get("type", "input_code"))
            name = item.get("name", item.get("owner", item.get("user", "")))
            lock_num = item.get("lock_number", self.config.lock_number)
            apt_num = item.get("apartment_number", item.get("apartment", None))

            identifiers.append(
                Identifier(
                    identifier_number=num,
                    identifier_type=id_type,
                    name=name,
                    item_uid=int(item_uid) if item_uid is not None else None,
                    link_id=int(link_id) if link_id is not None else None,
                    lock_number=lock_num,
                    apartment_number=str(apt_num) if apt_num is not None else None,
                    raw_data=item,
                )
            )
        return identifiers

    def find_code_identifier(
        self,
        name: Optional[str] = None,
        code: Optional[str] = None,
        link_id: Optional[int] = None,
    ) -> Optional[Identifier]:
        """Find an existing input_code identifier by name, code or link_id."""
        all_ids = self.get_identifiers(limit=500)
        code_ids = [i for i in all_ids if i.identifier_type in ("input_code", "code", "access_code")]

        # Match by link_id if available
        if link_id is not None:
            for item in code_ids:
                if item.link_id == link_id:
                    return item

        # Match by current code
        if code:
            for item in code_ids:
                if item.identifier_number == code:
                    return item

        # Match by name
        if name:
            clean_name = name.strip().lower()
            for item in code_ids:
                if item.name.strip().lower() == clean_name:
                    return item

        return None

    def create_identifier(
        self,
        code: str,
        name: str,
        lock_number: Optional[int] = None,
        link_id: Optional[int] = None,
        apartment_number: Optional[str] = None,
    ) -> Identifier:
        """
        Create a new access code identifier on the BAS-IP panel.
        POST /access/identifier
        Supports multiple identifier_type variants (input_code, access_code, code)
        to work seamlessly across different BAS-IP firmware versions.
        """
        lock = lock_number if lock_number is not None else self.config.lock_number
        type_candidates = ["input_code", "access_code", "code"]
        last_resp = None

        for id_type in type_candidates:
            payload: Dict[str, Any] = {
                "identifier_type": id_type,
                "identifier_number": str(code),
                "name": name,
                "lock_number": lock,
            }
            if link_id is not None:
                payload["link_id"] = link_id
            if apartment_number:
                payload["apartment_number"] = str(apartment_number)

            resp = self._request("POST", "/access/identifier", json=payload)
            if resp.status_code in (200, 201):
                res_data = resp.json() if resp.text else {}
                uid = None
                if isinstance(res_data, dict):
                    uid = res_data.get("id") or res_data.get("item_uid") or res_data.get("uid")

                logger.info(
                    "Created access code identifier for '%s' (uid=%s, type=%s) on panel %s",
                    name,
                    uid,
                    id_type,
                    self.config.host,
                )
                return Identifier(
                    identifier_number=str(code),
                    identifier_type=id_type,
                    name=name,
                    item_uid=int(uid) if uid is not None else None,
                    link_id=link_id,
                    lock_number=lock,
                    apartment_number=apartment_number,
                    raw_data=res_data if isinstance(res_data, dict) else {},
                )
            last_resp = resp
            if resp.status_code not in (400, 422):
                # Don't retry if it's 401 or 403 or 500
                break

        err_text = last_resp.text[:200] if last_resp else "Unknown error"
        status_code = last_resp.status_code if last_resp else 500
        raise BASIPError(f"Failed to create identifier on {self.config.host}: HTTP {status_code} - {err_text}")

    def update_identifier(
        self,
        item_uid: int,
        new_code: str,
        name: Optional[str] = None,
        lock_number: Optional[int] = None,
    ) -> bool:
        """
        Update an existing identifier on the BAS-IP panel.
        PATCH /access/identifier/item/{item_uid}
        If PATCH is not supported by older firmware, falls back to DELETE + POST.
        """
        payload: Dict[str, Any] = {"identifier_number": str(new_code)}
        if name:
            payload["name"] = name
        if lock_number is not None:
            payload["lock_number"] = lock_number

        resp = self._request("PATCH", f"/access/identifier/item/{item_uid}", json=payload)
        if resp.status_code in (200, 204):
            logger.info("Updated identifier uid=%s with new code on panel %s", item_uid, self.config.host)
            return True

        if resp.status_code == 405:
            # Fallback to DELETE + POST
            logger.warning(
                "PATCH not allowed (HTTP 405) on panel %s. Falling back to DELETE + POST.",
                self.config.host,
            )
            self.delete_identifier(item_uid)
            self.create_identifier(new_code, name or "", lock_number)
            return True

        raise BASIPError(f"Failed to update identifier uid={item_uid}: HTTP {resp.status_code} - {resp.text}")

    def delete_identifier(self, item_uid: int) -> bool:
        """Delete an identifier by UID: DELETE /access/identifier/item/{item_uid}."""
        resp = self._request("DELETE", f"/access/identifier/item/{item_uid}")
        if resp.status_code in (200, 204):
            logger.info("Deleted identifier uid=%s from panel %s", item_uid, self.config.host)
            return True
        raise BASIPError(f"Failed to delete identifier uid={item_uid}: HTTP {resp.status_code} - {resp.text}")

    def set_user_access_code(
        self,
        name: str,
        new_code: str,
        old_code: Optional[str] = None,
        link_id: Optional[int] = None,
        apartment_number: Optional[str] = None,
    ) -> Identifier:
        """
        High-level method to set or update a user's access code on the panel.
        Finds existing identifier if present and updates it, otherwise creates a new one.
        """
        existing = self.find_code_identifier(name=name, code=old_code, link_id=link_id)
        if existing and existing.item_uid is not None:
            logger.info(
                "Found existing identifier uid=%s for user '%s', updating code...",
                existing.item_uid,
                name,
            )
            self.update_identifier(
                item_uid=existing.item_uid,
                new_code=new_code,
                name=name,
                lock_number=self.config.lock_number,
            )
            existing.identifier_number = new_code
            return existing

        logger.info("No existing identifier found for user '%s', creating new one...", name)
        return self.create_identifier(
            code=new_code,
            name=name,
            lock_number=self.config.lock_number,
            link_id=link_id,
            apartment_number=apartment_number,
        )


class BASIPManager:
    """
    Coordinates access code updates across one or multiple BAS-IP AA-14FB panels
    (e.g., in a residential building complex with 38 panels and communal gates).
    Uses parallel thread pool for high-performance concurrent updates.
    """

    def __init__(self, panels: List[BASIPPanelConfig], max_workers: int = 20):
        self.panels = panels
        self.panel_map = {p.panel_id: p for p in panels}
        self.clients = {p.panel_id: BASIPClient(p) for p in panels}
        self.max_workers = max_workers

    def test_all_connections(self, max_workers: Optional[int] = None) -> Dict[str, Any]:
        """Test connection to every configured panel concurrently."""
        results: Dict[str, Any] = {}
        workers = max_workers or min(self.max_workers, len(self.clients) or 1)

        def _check_panel(item):
            pid, client = item
            key = f"{pid} [{client.config.location_str}] ({client.config.host}:{client.config.port})"
            try:
                ok, reason = client.check_connection(return_detail=True)
                return key, ok, reason
            except Exception as e:
                return key, False, str(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_panel = {executor.submit(_check_panel, item): item for item in self.clients.items()}
            for future in concurrent.futures.as_completed(future_to_panel):
                key, ok, reason = future.result()
                results[key] = (ok, reason)

        return results

    def get_target_panels_for_user(self, user: AccessCodeUser) -> List[BASIPPanelConfig]:
        """Returns the list of panels this specific user is allowed to access."""
        return [p for p in self.panels if user.can_access_panel(p)]

    def sync_user_code(
        self,
        name: str,
        new_code: str,
        old_code: Optional[str] = None,
        link_id: Optional[int] = None,
        user: Optional[AccessCodeUser] = None,
    ) -> Dict[str, Any]:
        """
        Sync a user's new access code to their assigned entrance panels and communal gates.
        Returns a dict of panel_desc -> (success: bool, error_detail: str).
        """
        if user is not None:
            target_configs = self.get_target_panels_for_user(user)
            apartment = user.apartment
        else:
            target_configs = [p for p in self.panels if p.enabled]
            apartment = None

        if not target_configs:
            logger.warning("No target panels found for user '%s'", name)
            return {}

        results: Dict[str, Any] = {}
        workers = min(self.max_workers, len(target_configs) or 1)

        def _sync_single(panel_cfg: BASIPPanelConfig):
            pid = panel_cfg.panel_id
            client = self.clients[pid]
            desc = f"{pid} [{panel_cfg.location_str}]"
            try:
                client.set_user_access_code(
                    name=name,
                    new_code=new_code,
                    old_code=old_code,
                    link_id=link_id,
                    apartment_number=apartment,
                )
                return desc, True, ""
            except Exception as e:
                err_detail = str(e)
                logger.error("Failed to sync code for '%s' to panel %s (%s): %s", name, pid, panel_cfg.host, err_detail)
                return desc, False, err_detail

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_panel = {executor.submit(_sync_single, p): p for p in target_configs}
            for future in concurrent.futures.as_completed(future_to_panel):
                desc, ok, err_detail = future.result()
                results[desc] = (ok, err_detail)

        return results
