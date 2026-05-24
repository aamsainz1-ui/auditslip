#!/usr/bin/env python3
"""Guard: public /api/pending cannot leak approval details; admin still sees full queue."""
from __future__ import annotations

import email.message
import hashlib
import importlib.util
import io
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(tempfile.mkdtemp(prefix="auditslip-pending-public-guard-")) / "auditslip.db"

os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(DB_PATH)
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "legacy-admin-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
Bot = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = Bot
bot_spec.loader.exec_module(Bot)
Bot.AuditslipBot(token="TEST_TOKEN", db_path=DB_PATH, dry_run=True).init_db()

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)
Dash.DB_PATH = DB_PATH

Dash.ensure_dashboard_tokens_table(DB_PATH)
admin_token = Dash.create_dashboard_token(DB_PATH, "admin", "admin-token")["token"]
admin_actor = hashlib.sha256(admin_token.encode("utf-8", "replace")).hexdigest()[:12]
secret_account = "1234567890"
pending_id = Dash.create_pending_action(
    DB_PATH,
    action="slip.delete",
    payload={"id": "SLIP-SECRET", "bot_key": "botA", "chat_id": "chat-secret", "account_no": secret_account, "reason": "public must not see this"},
    requested_by=admin_actor,
    request_id="req-public-guard",
)
assert pending_id > 0


class _FakeHandler(Dash.DashboardHandler):
    def __init__(self, path: str, token: str = "") -> None:
        self.client_address = ("127.0.0.1", 0)
        self.request_version = "HTTP/1.1"
        self.requestline = f"GET {path} HTTP/1.1"
        self.command = "GET"
        self.path = path
        self.rfile = io.BytesIO()
        self.wfile = io.BytesIO()
        self.headers = email.message.Message()
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
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


def get_pending(path: str, token: str = "") -> dict[str, Any]:
    handler = _FakeHandler(path, token)
    handler.do_GET()
    assert handler._status_code == 200, handler._response_body.decode("utf-8", "replace")
    return json.loads(handler._response_body.decode("utf-8"))


public_payload = get_pending("/api/pending?status=pending")
assert public_payload["ok"] is True, public_payload
assert public_payload.get("redacted") is True, public_payload
assert public_payload.get("items") == [], public_payload
assert public_payload.get("count") == 0, public_payload
assert public_payload.get("current_role") == "public", public_payload
assert "current_actor" not in public_payload, public_payload
assert public_payload.get("simple_approval_enabled") is False, public_payload
public_rendered = json.dumps(public_payload, ensure_ascii=False)
for forbidden in ["SLIP-SECRET", "botA", "chat-secret", secret_account, "public must not see this", admin_actor]:
    assert forbidden not in public_rendered, f"public /api/pending leaked {forbidden!r}: {public_rendered}"

# Public polling must not mutate pending rows by expiring/changing the queue.
with sqlite3.connect(DB_PATH) as conn:
    row = conn.execute("SELECT status FROM pending_actions WHERE id=?", (pending_id,)).fetchone()
assert row and row[0] == "pending", row

admin_payload = get_pending("/api/pending?status=pending", admin_token)
assert admin_payload["current_actor"] == admin_actor, admin_payload
assert admin_payload["current_role"] == "admin", admin_payload
assert admin_payload["count"] == 1, admin_payload
assert len(admin_payload["items"]) == 1, admin_payload
assert admin_payload["items"][0]["id"] == pending_id, admin_payload
assert admin_payload["items"][0]["requested_by"] == admin_actor, admin_payload
admin_rendered = json.dumps(admin_payload, ensure_ascii=False)
assert secret_account not in admin_rendered, "admin pending summary should stay PII-light"

print("ok: public /api/pending is redacted while admin pending listing still works")
