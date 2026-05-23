#!/usr/bin/env python3
"""Guard: /api/audit-chain/tail returns the last N entries in desc order WITHOUT raw payload
(no account numbers leaked) and surfaces request_id when the row was logged via
record_endpoint_mutation.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import threading
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(tempfile.mkdtemp(prefix="auditslip-audit-chain-tail-")) / "auditslip.db"

os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(DB_PATH)
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

ACCOUNT_NUMBER = "1234567890"  # sentinel: stored in payload so we can prove it doesn't leak

# Insert 10 mutations, each with the sentinel account number in the payload.
Dash.ensure_dashboard_mutation_log_table(DB_PATH)
for i in range(1, 11):
    Dash.record_endpoint_mutation(
        DB_PATH,
        action=f"act-{i}",
        actor=f"actor-{i}",
        request_id=f"abcdef{i:06d}",  # 12-hex like real uuid hex prefix
        payload={"account_no": ACCOUNT_NUMBER, "idx": i},
        result_status="ok",
        result_summary=f"row {i} summary",
        chat_id=f"chat-{i}",
        bot_key="default",
        slip_id=f"S{i}",
    )

# 1. Direct helper: returns 5 newest entries, no payload field, no account number anywhere.
entries = Dash.mutation_chain_tail(DB_PATH, limit=5)
assert len(entries) == 5, entries
ids = [e["id"] for e in entries]
assert ids == sorted(ids, reverse=True), ids
assert ids[0] == 10, ids
serialized = json.dumps(entries, ensure_ascii=False)
assert "payload_json" not in serialized, serialized
assert ACCOUNT_NUMBER not in serialized, "account number leaked in tail response"
for e in entries:
    assert "request_id" in e and e["request_id"], e
    # request_id surfaced from result_summary prefix, then summary is still present (truncated to 200 chars).
    assert len(e["result_summary"]) <= 200, e
    assert len(e["prev_hash"]) == 12 or e["prev_hash"] == "", e
    assert len(e["entry_hash"]) == 12, e

# 2. limit clamping: <1 -> 1, >500 -> 500, non-int -> 50 default.
assert len(Dash.mutation_chain_tail(DB_PATH, limit=0)) == 1
assert len(Dash.mutation_chain_tail(DB_PATH, limit=9999)) == 10  # only 10 rows exist
assert len(Dash.mutation_chain_tail(DB_PATH, limit="bogus")) == 10

# 3. Exercise the HTTP endpoint end-to-end (verify + tail) through the real ThreadingHTTPServer
# so we cover authorized() + the GET dispatch added in this phase.
Dash.DB_PATH = DB_PATH  # rebind module-level used by handlers
Dash.DASHBOARD_TOKEN = "test-token"

from http.server import ThreadingHTTPServer  # noqa: E402

server = ThreadingHTTPServer(("127.0.0.1", 0), Dash.DashboardHandler)
host, port = server.server_address
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    def get(path: str) -> tuple[int, dict]:
        conn = HTTPConnection(host, port, timeout=5)
        # Token via cookie so the URL stays clean (token-in-URL also works but redirects).
        conn.request("GET", path, headers={"Cookie": "auditslip_dashboard_token=test-token"})
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        conn.close()
        return resp.status, (json.loads(body) if body else {})

    status, body = get("/api/audit-chain/verify")
    assert status == 200, (status, body)
    assert body["ok"] is True, body
    assert body["total_rows"] == 10, body

    status, body = get("/api/audit-chain/tail?limit=5")
    assert status == 200, (status, body)
    assert body["ok"] is True, body
    assert len(body["entries"]) == 5, body
    assert body["entries"][0]["id"] == 10, body
    assert ACCOUNT_NUMBER not in json.dumps(body, ensure_ascii=False), "account number leaked via HTTP tail"

    # Unauthorized request -> 401, no leak.
    conn = HTTPConnection(host, port, timeout=5)
    conn.request("GET", "/api/audit-chain/tail?limit=5")
    resp = conn.getresponse()
    unauthorized_body = resp.read()
    assert resp.status == 401, (resp.status, unauthorized_body)
    conn.close()
finally:
    server.shutdown()
    server.server_close()

print("ok: /api/audit-chain/tail returns desc-ordered entries, no payload/account leakage, request_id surfaced")
