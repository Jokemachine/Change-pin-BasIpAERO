"""
Mock BAS-IP AA-14FB Intercom Server.
Emulates BAS-IP API for testing, development, and offline dry-runs.
"""
import hashlib
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class MockBASIPRequestHandler(BaseHTTPRequestHandler):
    """Handles BAS-IP AA-14FB API requests in-memory."""

    # In-memory storage shared across requests
    identifiers: Dict[int, Dict[str, Any]] = {}
    next_uid: int = 1
    admin_user: str = "admin"
    admin_password: str = "123456"
    valid_tokens = set()

    def log_message(self, format, *args):
        # Silence default stderr logging unless needed
        logger.debug("%s - - [%s] %s", self.client_address[0], self.log_date_time_string(), format % args)

    def _send_json(self, status_code: int, data: Any):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_auth(self) -> bool:
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            return token in self.valid_tokens
        if auth_header.startswith("Basic "):
            import base64
            try:
                decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
                user, pwd = decoded.split(":", 1)
                return user == self.admin_user and pwd == self.admin_password
            except Exception:
                return False
        return False

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # Login endpoint: /api/v1/login or /api/v0/login or /login
        if path.endswith("/login"):
            username = query.get("username", [""])[0]
            password_hash = query.get("password", [""])[0]
            expected_hash = hashlib.md5(self.admin_password.encode("utf-8")).hexdigest().upper()

            if username == self.admin_user and password_hash == expected_hash:
                token = "mock-token-" + hashlib.md5(f"{username}".encode()).hexdigest()
                self.valid_tokens.add(token)
                return self._send_json(200, {"token": token, "account_type": "admin"})
            return self._send_json(401, {"error": "Invalid credentials"})

        # Device info: /api/info
        if path.endswith("/api/info") or path.endswith("/info"):
            return self._send_json(200, {
                "device_model": "AA-14FB",
                "firmware_version": "1.7.0",
                "api_version": "1.7.0",
                "device_name": "AA-14FB Entrance Panel",
            })

        # Identifiers list: /access/identifiers/items/list or /access/identifier/items or /access/identifiers
        if any(p in path for p in ("/access/identifiers/items/list", "/access/identifier/items", "/access/identifiers")):
            if not self._check_auth():
                return self._send_json(401, {"error": "Unauthorized"})

            items = list(self.identifiers.values())
            return self._send_json(200, {
                "list_items": items,
                "list_option": {
                    "pagination": {
                        "total_items": len(items),
                        "items_limit": 100,
                        "total_pages": 1,
                        "current_page": 1,
                    }
                }
            })

        # Single identifier: /access/identifiers/item/{uid} or /access/identifier/item/{uid}
        if "/access/identifiers/item/" in path or "/access/identifier/item/" in path:
            if not self._check_auth():
                return self._send_json(401, {"error": "Unauthorized"})
            try:
                base_part = "/access/identifiers/item/" if "/access/identifiers/item/" in path else "/access/identifier/item/"
                uid = int(path.split(base_part)[1].split("/")[0])
                if uid in self.identifiers:
                    return self._send_json(200, self.identifiers[uid])
                return self._send_json(404, {"error": "Identifier not found"})
            except ValueError:
                return self._send_json(400, {"error": "Invalid UID"})

        return self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)
        body = json.loads(post_data.decode("utf-8")) if post_data else {}

        # Alternative login via POST
        if path.endswith("/login") or path.endswith("/devices/login"):
            login = body.get("login") or body.get("username")
            pwd = body.get("password")
            if login == self.admin_user and pwd == self.admin_password:
                token = "mock-token-post"
                self.valid_tokens.add(token)
                return self._send_json(200, {"token": token, "account_type": "admin"})
            return self._send_json(401, {"error": "Invalid credentials"})

        if not self._check_auth():
            return self._send_json(401, {"error": "Unauthorized"})

        # Create identifier: /access/identifiers/item or /access/identifier or /access/identifiers
        if any(path.endswith(ep) for ep in ("/access/identifiers/item", "/access/identifier", "/access/identifiers")):
            uid = MockBASIPRequestHandler.next_uid
            MockBASIPRequestHandler.next_uid += 1

            # Extract name and owner
            owner_obj = body.get("identifier_owner")
            if isinstance(owner_obj, dict):
                owner_name = owner_obj.get("name", "")
                owner_type = owner_obj.get("type", "owner")
            else:
                owner_name = str(body.get("name") or owner_obj or "")
                owner_type = "owner"

            lock_val = body.get("lock", body.get("lock_number", 1))

            identifier_item = {
                "identifier_id": uid,
                "identifier_uid": uid,
                "item_uid": uid,
                "identifier_type": body.get("identifier_type", "inputCode"),
                "identifier_number": str(body.get("identifier_number", "")),
                "identifier_owner": {
                    "name": owner_name,
                    "type": owner_type,
                },
                "name": owner_name,
                "lock": lock_val,
                "lock_number": 2 if lock_val == "second" else 1,
                "link_id": body.get("link_id"),
            }
            MockBASIPRequestHandler.identifiers[uid] = identifier_item
            return self._send_json(201, {
                "uid": uid,
                "id": uid,
                "item_uid": uid,
                "identifier_uid": uid,
                "message": "Identifier created",
            })

        return self._send_json(404, {"error": "Not Found"})

    def do_PATCH(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if not self._check_auth():
            return self._send_json(401, {"error": "Unauthorized"})

        if "/access/identifiers/item/" in path or "/access/identifier/item/" in path:
            try:
                base_part = "/access/identifiers/item/" if "/access/identifiers/item/" in path else "/access/identifier/item/"
                uid = int(path.split(base_part)[1].split("/")[0])
                if uid not in self.identifiers:
                    return self._send_json(404, {"error": "Identifier not found"})

                content_length = int(self.headers.get("Content-Length", 0))
                post_data = self.rfile.read(content_length)
                body = json.loads(post_data.decode("utf-8")) if post_data else {}

                item = self.identifiers[uid]
                base_info = body.get("base", body)

                if "identifier_number" in base_info:
                    item["identifier_number"] = str(base_info["identifier_number"])

                owner_info = base_info.get("identifier_owner")
                if isinstance(owner_info, dict) and "name" in owner_info:
                    item["identifier_owner"]["name"] = owner_info["name"]
                    item["name"] = owner_info["name"]
                elif "name" in base_info:
                    item["name"] = base_info["name"]
                    if "identifier_owner" in item and isinstance(item["identifier_owner"], dict):
                        item["identifier_owner"]["name"] = base_info["name"]

                if "lock" in base_info:
                    item["lock"] = base_info["lock"]
                if "lock_number" in base_info:
                    item["lock_number"] = base_info["lock_number"]

                return self._send_json(200, item)
            except ValueError:
                return self._send_json(400, {"error": "Invalid UID"})

        return self._send_json(404, {"error": "Not Found"})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if not self._check_auth():
            return self._send_json(401, {"error": "Unauthorized"})

        if "/access/identifiers/item/" in path or "/access/identifier/item/" in path or "/access/identifier/" in path:
            try:
                for prefix in ("/access/identifiers/item/", "/access/identifier/item/", "/access/identifier/"):
                    if prefix in path:
                        uid_str = path.split(prefix)[1].split("/")[0]
                        if uid_str.isdigit():
                            uid = int(uid_str)
                            if uid in self.identifiers:
                                del self.identifiers[uid]
                                return self._send_json(200, {"message": "Deleted"})
                            return self._send_json(404, {"error": "Identifier not found"})
                return self._send_json(400, {"error": "Invalid UID"})
            except ValueError:
                return self._send_json(400, {"error": "Invalid UID"})

        return self._send_json(404, {"error": "Not Found"})


class MockBASIPServer:
    """Threaded Mock BAS-IP AA-14FB server for test environments."""

    def __init__(self, host: str = "127.0.0.1", port: int = 18080):
        self.host = host
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self):
        MockBASIPRequestHandler.identifiers.clear()
        MockBASIPRequestHandler.next_uid = 1
        MockBASIPRequestHandler.valid_tokens.clear()
        self.server = HTTPServer((self.host, self.port), MockBASIPRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        logger.info("Mock BAS-IP server started at http://%s:%s", self.host, self.port)

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logger.info("Mock BAS-IP server stopped.")
