#!/usr/bin/env python3
"""Guard: dashboard RBAC blocks destructive endpoints based on actor role.

Drives the HTTP handler in-process with a fake socket so we can assert the
status code each role gets for each guarded endpoint.
"""
from __future__ import annotations

import email.message
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
from http import HTTPStatus
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-rbac-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-rbac-export-")))
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "legacy-admin-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True)
bot.init_db()

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

DB_PATH = Path(os.environ["AUDITSLIP_DB"])


# --- Prepare role tokens ---------------------------------------------------
Dash.ensure_dashboard_tokens_table(DB_PATH)
ROLE_TOKENS: Dict[str, str] = {}
for role in ("admin", "auditor", "operator", "viewer"):
    result = Dash.create_dashboard_token(DB_PATH, role, f"{role}-test")
    assert result.get("ok"), result
    ROLE_TOKENS[role] = result["token"]


# --- Handler harness -------------------------------------------------------
class _FakeHandler(Dash.DashboardHandler):
    """Drive DashboardHandler without a real socket.

    We bypass BaseHTTPRequestHandler.__init__ entirely (it would try to .makefile
    a real socket) and feed the handler a request via attributes directly.
    """

    def __init__(self, method: str, path: str, token: str, body: bytes = b"") -> None:  # noqa: D401
        # Intentionally skip parent __init__.
        self.client_address = ("127.0.0.1", 0)
        self.request_version = "HTTP/1.1"
        self.requestline = f"{method} {path} HTTP/1.1"
        self.command = method
        self.path = path
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.headers = email.message.Message()
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self.headers["X-Auditslip-Action"] = "dashboard"
        if body:
            self.headers["Content-Type"] = "application/json"
            self.headers["Content-Length"] = str(len(body))
        # send_response uses these attributes.
        self._status_code: int = 0
        self._sent_headers: List[Tuple[str, str]] = []
        self._response_body: bytes = b""

    # Override low-level wire methods so we capture status without parsing raw bytes.
    def send_response(self, code: int, message: str | None = None) -> None:  # type: ignore[override]
        self._status_code = int(code)

    def send_header(self, keyword: str, value: str) -> None:  # type: ignore[override]
        self._sent_headers.append((keyword, value))

    def end_headers(self) -> None:  # type: ignore[override]
        return

    def log_message(self, fmt: str, *args: Any) -> None:  # type: ignore[override]
        return

    # Override send_bytes so we capture body + status reliably.
    def send_bytes(self, status: int, body: bytes, content_type: str, extra_headers=None) -> None:  # type: ignore[override]
        self._status_code = int(status)
        self._response_body = bytes(body)

    def send_json(self, obj: Any, status: int = 200) -> None:  # type: ignore[override]
        self._status_code = int(status)
        self._response_body = json.dumps(obj, ensure_ascii=False).encode("utf-8")


def post(path: str, token: str, payload: Dict[str, Any] | None = None) -> int:
    body = json.dumps(payload or {}).encode("utf-8")
    h = _FakeHandler("POST", path, token, body=body)
    h.do_POST()
    return h._status_code


# --- Endpoint role matrix --------------------------------------------------
DESTRUCTIVE: Dict[str, set] = {
    "/api/slip/delete": {"admin"},
    "/api/duplicate/unmark": {"admin", "operator"},
    "/api/account-limit": {"admin"},
    "/api/company-account": {"admin"},
    "/api/slip/reprocess": {"admin", "operator"},
    "/api/reconcile": {"admin"},
    "/api/close": {"admin"},
    "/api/bank-review/openai": {"admin", "operator"},
    "/api/bank-review/openai-all": {"admin"},
}

UNAUTHORIZED = int(HTTPStatus.UNAUTHORIZED)
NOT_FOUND = int(HTTPStatus.NOT_FOUND)

failures: List[str] = []
for endpoint, allowed in DESTRUCTIVE.items():
    for role in ("admin", "auditor", "operator", "viewer"):
        tok = ROLE_TOKENS[role]
        status = post(endpoint, tok, {})
        permitted = role in allowed
        if permitted:
            # When permitted, status must NOT be 401 (request reached the body —
            # any 200/400/404 is fine, just not blocked by RBAC).
            if status == UNAUTHORIZED:
                failures.append(f"role={role} endpoint={endpoint} expected pass got 401")
        else:
            if status != UNAUTHORIZED:
                failures.append(f"role={role} endpoint={endpoint} expected 401 got {status}")

# Unauthenticated (no token) must also 401 every destructive endpoint.
for endpoint in DESTRUCTIVE:
    status = post(endpoint, token="", payload={})
    if status != UNAUTHORIZED:
        failures.append(f"no-token endpoint={endpoint} expected 401 got {status}")

assert not failures, "RBAC guard failures:\n  - " + "\n  - ".join(failures)

# Sanity: viewer cannot delete, operator can reprocess but not delete, admin can both.
assert post("/api/slip/delete", ROLE_TOKENS["viewer"], {}) == UNAUTHORIZED
assert post("/api/slip/delete", ROLE_TOKENS["operator"], {}) == UNAUTHORIZED
assert post("/api/slip/reprocess", ROLE_TOKENS["operator"], {}) != UNAUTHORIZED
assert post("/api/slip/reprocess", ROLE_TOKENS["admin"], {}) != UNAUTHORIZED
assert post("/api/slip/delete", ROLE_TOKENS["admin"], {}) != UNAUTHORIZED

print("ok: Auditslip dashboard RBAC guards destructive endpoints by role")
