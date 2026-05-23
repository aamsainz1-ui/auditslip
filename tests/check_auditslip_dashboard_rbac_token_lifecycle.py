#!/usr/bin/env python3
"""Guard: dashboard_tokens lifecycle — bootstrap, create, use, revoke, last-admin protection."""
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
from http import HTTPStatus
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-rbac-lc-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-rbac-lc-export-")))
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"
LEGACY_TOKEN = "legacy-admin-token"
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = LEGACY_TOKEN

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


# --- Handler harness (same shape as the guard test) ------------------------
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
        self._response_body: bytes = b""

    def send_response(self, code: int, message: str | None = None) -> None:  # type: ignore[override]
        self._status_code = int(code)

    def send_header(self, keyword: str, value: str) -> None:  # type: ignore[override]
        return

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


def call(method: str, path: str, token: str, payload: Dict[str, Any] | None = None) -> Tuple[int, Dict[str, Any]]:
    body = json.dumps(payload or {}).encode("utf-8") if method == "POST" else b""
    h = _FakeHandler(method, path, token, body=body)
    if method == "POST":
        h.do_POST()
    else:
        h.do_GET()
    try:
        return h._status_code, json.loads(h._response_body.decode("utf-8") or "{}")
    except Exception:
        return h._status_code, {}


UNAUTHORIZED = int(HTTPStatus.UNAUTHORIZED)


# --- 1) Bootstrap admin token ---------------------------------------------
Dash.ensure_dashboard_tokens_table(DB_PATH)
# Pre-bootstrap: legacy token still works because actor_role falls back to admin
# when the legacy hash is not yet in the table.
assert Dash.lookup_dashboard_token_role(DB_PATH, LEGACY_TOKEN) == "", "legacy hash should not be in db pre-bootstrap"

Dash.bootstrap_dashboard_admin_token(DB_PATH, LEGACY_TOKEN)
assert Dash.lookup_dashboard_token_role(DB_PATH, LEGACY_TOKEN) == "admin", "legacy token should be admin after bootstrap"

# Idempotent: calling bootstrap again does not insert duplicates.
with sqlite3.connect(DB_PATH) as _con:
    cnt_before = _con.execute("SELECT COUNT(*) FROM dashboard_tokens").fetchone()[0]
# Reset bootstrap flag to simulate a fresh process picking up an already-bootstrapped DB.
Dash._DASHBOARD_TOKENS_BOOTSTRAPPED = False
Dash.bootstrap_dashboard_admin_token(DB_PATH, LEGACY_TOKEN)
with sqlite3.connect(DB_PATH) as _con:
    cnt_after = _con.execute("SELECT COUNT(*) FROM dashboard_tokens").fetchone()[0]
assert cnt_before == cnt_after, f"bootstrap not idempotent: {cnt_before} -> {cnt_after}"


# --- 2) Create operator token via admin --------------------------------------
status, body = call("POST", "/api/tokens/create", LEGACY_TOKEN, {"role": "operator", "label": "phase-b operator"})
assert status == 200 and body.get("ok"), (status, body)
operator_token = body["token"]
operator_prefix = body["token_hash_prefix"]
assert len(operator_token) == 64, operator_token  # 32 bytes hex
assert Dash.lookup_dashboard_token_role(DB_PATH, operator_token) == "operator"


# --- 3) Operator can reprocess; cannot delete --------------------------------
status, _ = call("POST", "/api/slip/reprocess", operator_token, {"id": "nope"})
assert status != UNAUTHORIZED, f"operator should reach reprocess body, got {status}"

status, _ = call("POST", "/api/slip/delete", operator_token, {"id": "nope"})
assert status == UNAUTHORIZED, f"operator must be blocked from delete, got {status}"


# --- 4) Admin can list tokens; non-admin cannot ------------------------------
status, body = call("GET", "/api/tokens", LEGACY_TOKEN)
assert status == 200 and body.get("ok"), (status, body)
roles = sorted({t["role"] for t in body.get("tokens", [])})
assert "admin" in roles and "operator" in roles, body
for tok_row in body.get("tokens", []):
    assert len(tok_row["token_hash_prefix"]) == 12, tok_row  # masked
status, _ = call("GET", "/api/tokens", operator_token)
assert status == UNAUTHORIZED, status


# --- 5) Revoke operator -> operator can no longer authorize ------------------
status, body = call("POST", "/api/tokens/revoke", LEGACY_TOKEN, {"token_hash_prefix": operator_prefix})
assert status == 200 and body.get("ok"), (status, body)
assert Dash.lookup_dashboard_token_role(DB_PATH, operator_token) == "", "revoked operator should resolve to empty role"
status, _ = call("POST", "/api/slip/reprocess", operator_token, {"id": "nope"})
assert status == UNAUTHORIZED, f"revoked operator must be blocked, got {status}"


# --- 6) Cannot revoke the last admin -----------------------------------------
# Currently only one admin (legacy-bootstrap). Get its hash prefix.
admin_hash_prefix = hashlib.sha256(LEGACY_TOKEN.encode("utf-8")).hexdigest()[:12]
status, body = call("POST", "/api/tokens/revoke", LEGACY_TOKEN, {"token_hash_prefix": admin_hash_prefix})
assert status == 400 and not body.get("ok"), (status, body)
assert "last admin" in (body.get("error") or "").lower(), body
# Confirm the admin is still active.
assert Dash.lookup_dashboard_token_role(DB_PATH, LEGACY_TOKEN) == "admin"

# Create a second admin, then revoking the first should succeed.
status, body = call("POST", "/api/tokens/create", LEGACY_TOKEN, {"role": "admin", "label": "second-admin"})
assert status == 200 and body.get("ok"), (status, body)
second_admin_token = body["token"]
second_admin_prefix = body["token_hash_prefix"]
status, body = call("POST", "/api/tokens/revoke", second_admin_token, {"token_hash_prefix": admin_hash_prefix})
assert status == 200 and body.get("ok"), (status, body)
# Legacy admin should now be unable to authorize (only second_admin active).
assert Dash.lookup_dashboard_token_role(DB_PATH, LEGACY_TOKEN) == ""
# Second admin is the last admin — revoking it must fail with "last admin".
status, body = call("POST", "/api/tokens/revoke", second_admin_token, {"token_hash_prefix": second_admin_prefix})
assert status == 400 and "last admin" in (body.get("error") or "").lower(), body

print("ok: Auditslip dashboard RBAC token lifecycle (bootstrap, create, revoke, last-admin)")
