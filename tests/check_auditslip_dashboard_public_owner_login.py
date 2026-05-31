#!/usr/bin/env python3
"""Guard: dashboard read-only access is public; admin uses owner/password, not URL token."""
from __future__ import annotations

import email.message
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
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-public-owner-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-public-owner-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "legacy-admin-token"
os.environ["AUDITSLIP_DASHBOARD_OWNER_USER"] = "owner"
os.environ["AUDITSLIP_DASHBOARD_OWNER_PASSWORD"] = "test-owner-pass"
os.environ["AUDITSLIP_TWALLET_TIMEOUT"] = "0.01"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

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


class _FakeHandler(Dash.DashboardHandler):
    """Drive DashboardHandler without a real socket."""

    def __init__(self, method: str, path: str, *, token: str = "", cookie: str = "", body: bytes = b"") -> None:
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
        if cookie:
            self.headers["Cookie"] = cookie
        self.headers["X-Auditslip-Action"] = "dashboard"
        if body:
            self.headers["Content-Type"] = "application/json"
            self.headers["Content-Length"] = str(len(body))
        self._status_code: int = 0
        self._sent_headers: List[Tuple[str, str]] = []

    def send_response(self, code: int, message: str | None = None) -> None:  # type: ignore[override]
        self._status_code = int(code)

    def send_header(self, keyword: str, value: str) -> None:  # type: ignore[override]
        self._sent_headers.append((keyword, value))

    def end_headers(self) -> None:  # type: ignore[override]
        return

    def log_message(self, fmt: str, *args: Any) -> None:  # type: ignore[override]
        return

    def json_body(self) -> Dict[str, Any]:
        return json.loads(self.wfile.getvalue().decode("utf-8") or "{}")


def request(method: str, path: str, *, token: str = "", cookie: str = "", payload: Dict[str, Any] | None = None) -> _FakeHandler:
    body = json.dumps(payload or {}).encode("utf-8") if payload is not None else b""
    h = _FakeHandler(method, path, token=token, cookie=cookie, body=body)
    if method == "GET":
        h.do_GET()
    else:
        h.do_POST()
    return h


# Public read-only entry points must not require a dashboard token.
assert request("GET", "/")._status_code == int(HTTPStatus.OK)
summary = request("GET", "/api/summary?detail=lite")
assert summary._status_code == int(HTTPStatus.OK), summary.wfile.getvalue()[:200]
summary_data = summary.json_body()
assert "totals" in summary_data and "selected_bot_key" in summary_data, summary_data.keys()

# Admin-only endpoints, audit-chain internals, and mutations stay blocked without auth.
assert request("GET", "/api/tokens")._status_code == int(HTTPStatus.UNAUTHORIZED)
assert request("GET", "/api/audit-chain/tail?limit=5")._status_code == int(HTTPStatus.UNAUTHORIZED)
assert request("POST", "/api/account-limit", payload={})._status_code == int(HTTPStatus.UNAUTHORIZED)

# Owner/password login creates an admin session cookie; wrong password is rejected.
wrong = request("POST", "/api/login", payload={"username": "owner", "password": "wrong"})
assert wrong._status_code == int(HTTPStatus.UNAUTHORIZED)
login = request("POST", "/api/login", payload={"username": "owner", "password": "test-owner-pass"})
assert login._status_code == int(HTTPStatus.OK), login.wfile.getvalue()
login_data = login.json_body()
assert login_data.get("ok") is True and login_data.get("role") == "admin", login_data
assert "test-owner-pass" not in login.wfile.getvalue().decode("utf-8")
set_cookie = next(v for k, v in login._sent_headers if k.lower() == "set-cookie")
session_cookie = set_cookie.split(";", 1)[0]
assert session_cookie.startswith(Dash.COOKIE_NAME + "=")

# The owner session grants admin role without URL tokens, but malformed mutations are rejected.
assert request("GET", "/api/tokens", cookie=session_cookie)._status_code == int(HTTPStatus.OK)
blank_limit = request("POST", "/api/account-limit?approval=request", cookie=session_cookie, payload={})
assert blank_limit._status_code == int(HTTPStatus.BAD_REQUEST), (blank_limit._status_code, blank_limit.wfile.getvalue())
with Dash.connect(Path(os.environ["AUDITSLIP_DB"])) as conn:
    Dash.ensure_account_limit_table(conn)
    blank_rows = conn.execute("SELECT COUNT(*) AS c FROM account_limits WHERE chat_id='' OR limit_key='' OR account='' ").fetchone()
assert int(blank_rows["c"] if blank_rows else 0) == 0

# Account-limit settings are direct operational saves, not pending approvals.
valid_limit = request(
    "POST",
    "/api/account-limit?approval=request",
    cookie=session_cookie,
    payload={
        "chat_id": "bot:bot6",
        "limit_key": "scb|x0522",
        "display_name": "บัญชีถอน",
        "bank": "SCB",
        "account": "xxx-xxx052-2",
        "limit_amount": 123456,
    },
)
assert valid_limit._status_code == int(HTTPStatus.OK), (valid_limit._status_code, valid_limit.wfile.getvalue())
valid_data = valid_limit.json_body()
assert valid_data.get("ok") is True and valid_data.get("status") == "saved", valid_data
assert "pending_id" not in valid_data, valid_data
with Dash.connect(Path(os.environ["AUDITSLIP_DB"])) as conn:
    saved = conn.execute("SELECT limit_amount FROM account_limits WHERE chat_id=? AND limit_key=?", ("bot:bot6", "scb|x0522")).fetchone()
Dash.ensure_pending_actions_table(Path(os.environ["AUDITSLIP_DB"]))
with Dash.connect(Path(os.environ["AUDITSLIP_DB"])) as conn:
    pending_count = conn.execute("SELECT COUNT(*) AS c FROM pending_actions WHERE action='account.limit'").fetchone()
assert saved and float(saved["limit_amount"]) == 123456.0, saved
assert int(pending_count["c"] if pending_count else 0) == 0

# Rendered dashboard exposes the no-token owner-login UI.
html = Dash.render_dashboard_html("legacy-admin-token")
for marker in ["adminUsername", "adminPassword", "/api/login", "เข้าสู่ระบบ Admin"]:
    assert marker in html, marker

print("ok: public no-token dashboard with owner/password admin login")
