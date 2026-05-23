#!/usr/bin/env python3
"""Guard: single-token admin can use simple approval mode to approve+execute own pending action."""
from __future__ import annotations

import email.message
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot6:BOT_TOKEN:บริษัท 6"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-simple-approval-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-simple-approval-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "legacy-admin-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"
os.environ["AUDITSLIP_ALERT_ON_MUTATION"] = "0"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)
db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="bot6", company_name="บริษัท 6")
bot.init_db()

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)
DB_PATH = Path(os.environ["AUDITSLIP_DB"])
Dash.ensure_dashboard_tokens_table(DB_PATH)
admin_token = Dash.create_dashboard_token(DB_PATH, "admin", "only-admin")["token"]
admin_actor = hashlib.sha256(admin_token.encode("utf-8", "replace")).hexdigest()[:12]
assert Dash.active_dashboard_token_count(DB_PATH) == 1
assert Dash.simple_approval_enabled(DB_PATH, admin_actor, "admin") is True

pending_id = Dash.create_pending_action(
    DB_PATH,
    action="account.limit",
    payload={
        "chat_id": "bot:bot6",
        "limit_key": "kbank|x7061",
        "display_name": "บัญชีถอนหนึ่ง",
        "bank": "KBANK",
        "account": "x-7061",
        "limit_amount": 12345,
    },
    requested_by=admin_actor,
    request_id="req-simple-limit",
)
assert Dash.load_pending_action(DB_PATH, pending_id)["status"] == "pending"

class _FakeHandler(Dash.DashboardHandler):
    def __init__(self, method: str, path: str, token: str, body: bytes = b"") -> None:
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
        self._status_code: int = 0
        self._sent_headers: List[Tuple[str, str]] = []
        self._response_body: bytes = b""

    def send_response(self, code: int, message: str | None = None) -> None:  # type: ignore[override]
        self._status_code = int(code)

    def send_header(self, keyword: str, value: str) -> None:  # type: ignore[override]
        self._sent_headers.append((keyword, value))

    def end_headers(self) -> None:  # type: ignore[override]
        return

    def log_message(self, fmt: str, *args: Any) -> None:  # type: ignore[override]
        return

    def send_bytes(self, status: int, body: bytes, content_type: str, extra_headers=None) -> None:  # type: ignore[override]
        self._status_code = int(status)
        self._response_body = bytes(body)

    def send_json(self, obj: Any, status: int = 200) -> None:  # type: ignore[override]
        self._status_code = int(status)
        self._response_body = json.dumps(obj, ensure_ascii=False).encode("utf-8")

body = json.dumps({"pending_id": pending_id}).encode("utf-8")
handler = _FakeHandler("POST", "/api/pending/approve?approval=execute", admin_token, body)
handler.do_POST()
assert handler._status_code == 200, handler._response_body.decode("utf-8", "replace")
result = json.loads(handler._response_body.decode("utf-8"))
assert result["ok"] is True, result
assert result["status"] == "executed", result
row = Dash.load_pending_action(DB_PATH, pending_id)
assert row["status"] == "executed", row

with Dash.connect(DB_PATH) as conn:
    saved = conn.execute("SELECT limit_amount FROM account_limits WHERE chat_id=? AND limit_key=?", ("bot:bot6", "kbank|x7061")).fetchone()
assert saved and float(saved["limit_amount"]) == 12345.0, saved

pending_payload = None
handler_get = _FakeHandler("GET", "/api/pending?status=all", admin_token)
handler_get.do_GET()
assert handler_get._status_code == 200, handler_get._response_body.decode("utf-8", "replace")
pending_payload = json.loads(handler_get._response_body.decode("utf-8"))
assert pending_payload["simple_approval_enabled"] is True, pending_payload
assert pending_payload["current_actor"] == admin_actor, pending_payload

html = Dash.render_dashboard_html("test-token")
for marker in ["simple_approval_enabled", "โหมดง่าย", "อนุมัติ+ทำรายการ", "approval=execute"]:
    assert marker in html, marker

print("ok: single-token admin simple approval executes pending account limit")
