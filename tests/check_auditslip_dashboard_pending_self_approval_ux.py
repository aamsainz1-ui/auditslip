#!/usr/bin/env python3
"""Guard: pending approval UI explains self-approval before the user taps Approve."""
from __future__ import annotations

import email.message
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-self-approve-ux-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-self-approve-ux-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "legacy-admin-token"
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
DB_PATH = Path(os.environ["AUDITSLIP_DB"])

Dash.ensure_dashboard_tokens_table(DB_PATH)
admin_token = Dash.create_dashboard_token(DB_PATH, "admin", "admin-requester")["token"]
admin_actor = hashlib.sha256(admin_token.encode("utf-8", "replace")).hexdigest()[:12]
pending_id = Dash.create_pending_action(
    DB_PATH,
    action="slip.delete",
    payload={"id": "SLIP_SELF", "bot_key": "__all__", "reason": "dashboard operator delete"},
    requested_by=admin_actor,
    request_id="req-self-approve",
)
assert pending_id > 0


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


handler = _FakeHandler("GET", "/api/pending?status=pending", admin_token)
handler.do_GET()
assert handler._status_code == 200, handler._response_body.decode("utf-8", "replace")
payload = json.loads(handler._response_body.decode("utf-8"))
assert payload["current_actor"] == admin_actor, payload
assert payload["current_role"] == "admin", payload
assert payload["items"][0]["requested_by"] == admin_actor, payload

html = Dash.render_dashboard_html("test-token")
scripts = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
for marker in [
    "pendingRowsTable(rows, currentActor)",
    "const isSelfRequest = currentActor && String(r.requested_by || '') === String(currentActor);",
    "ใช้ token อื่นอนุมัติ",
    "คำขอที่คุณสร้างเอง",
    "data.current_actor",
]:
    assert marker in scripts or marker in html, marker

print("ok: pending approval UI disables/explains self-approval with current actor evidence")
