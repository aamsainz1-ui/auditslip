#!/usr/bin/env python3
"""Guard: /api/health reports read-only operational checks, not just app reachability."""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="auditslip-health-test-"))
DB_PATH = TMP / "auditslip.db"
WATCHDOG_STATE = TMP / "watchdog-state.json"

os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(DB_PATH)
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["AUDITSLIP_WATCHDOG_STATE"] = str(WATCHDOG_STATE)
os.environ["AUDITSLIP_HEALTH_SYSTEMCTL"] = "0"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert spec and spec.loader
Dash = importlib.util.module_from_spec(spec)
sys.modules["auditslip_dashboard"] = Dash
spec.loader.exec_module(Dash)

Dash.AuditslipBot(token="TEST_TOKEN", db_path=DB_PATH, dry_run=True).init_db()
Dash.ensure_pending_actions_table(DB_PATH)
now_ms = int(time.time() * 1000)
today = "2026-05-24"
old_ms = now_ms - 45 * 60 * 1000
fresh_ms = now_ms - 2 * 60 * 1000
with sqlite3.connect(DB_PATH) as conn:
    conn.execute(
        """
        INSERT INTO slips(id, bot_key, company_name, chat_id, status, slip_date_iso,
                          amount, is_duplicate, created_at, created_at_iso)
        VALUES
          ('S1','botA','Company A','chatA','success',?,150.25,0,?, '2026-05-24T08:00:00+07:00'),
          ('S2','botA','Company A','chatA','success',?,999.00,1,?, '2026-05-24T08:05:00+07:00')
        """,
        (today, now_ms, today, now_ms),
    )
    conn.execute(
        """
        INSERT INTO ocr_jobs(job_id, slip_id, bot_key, company_name, chat_id, file_id,
                             status, attempts, max_attempts, next_run_at, created_at, updated_at)
        VALUES
          ('J-QUEUED-STALE','S3','botA','Company A','chatA','fileA','queued',0,3,0,?,?),
          ('J-PROCESSING-FRESH','S4','botA','Company A','chatA','fileB','processing',1,3,0,?,?),
          ('J-FAILED','S5','botA','Company A','chatA','fileC','failed',3,3,0,?,?)
        """,
        (old_ms, old_ms, fresh_ms, fresh_ms, fresh_ms, fresh_ms),
    )
    conn.commit()
Dash.create_pending_action(
    DB_PATH,
    action="delete_slip",
    payload={"slip_id": "S1", "account_no": "1234567890"},
    requested_by="actor-test",
    request_id="req-health",
)
WATCHDOG_STATE.write_text(json.dumps({"last_ok_at": "test", "secret_token": "SHOULD_NOT_LEAK"}), encoding="utf-8")
os.utime(WATCHDOG_STATE, (time.time() - 120, time.time() - 120))

Dash.DB_PATH = DB_PATH
Dash.DASHBOARD_TOKEN = "test-token"


def table_counts() -> dict[str, int]:
    with sqlite3.connect(DB_PATH) as conn:
        return {
            "slips": conn.execute("SELECT COUNT(*) FROM slips").fetchone()[0],
            "ocr_jobs": conn.execute("SELECT COUNT(*) FROM ocr_jobs").fetchone()[0],
            "pending_actions": conn.execute("SELECT COUNT(*) FROM pending_actions").fetchone()[0],
        }


from http.server import ThreadingHTTPServer  # noqa: E402

server = ThreadingHTTPServer(("127.0.0.1", 0), Dash.DashboardHandler)
host, port = server.server_address
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    before = table_counts()
    quick_conn = HTTPConnection(host, port, timeout=5)
    quick_conn.request("GET", "/api/health?quick=1")  # watchdog reachability probe: cheap and public
    quick_resp = quick_conn.getresponse()
    quick_raw = quick_resp.read().decode("utf-8")
    quick_conn.close()
    conn = HTTPConnection(host, port, timeout=5)
    conn.request("GET", "/api/health")  # public full operational endpoint; no auth cookie required
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    after = table_counts()
finally:
    server.shutdown()
    server.server_close()

assert resp.status == 200, (resp.status, raw)
body = json.loads(raw)
quick_body = json.loads(quick_raw)
assert quick_resp.status == 200, (quick_resp.status, quick_raw)
assert quick_body["ok"] is True and quick_body["quick"] is True, quick_body
assert "ocr_queue" not in quick_body["checks"], quick_body  # watchdog quick probe avoids aggregate queue scans
assert before == after, (before, after, body, quick_body)  # health must be read-only
assert body["ok"] is True, body
assert body["app"] == Dash.APP_NAME, body
checks = body["checks"]
for key in ["db", "schema", "slips", "ocr_queue", "pending_actions", "watchdog"]:
    assert key in checks, (key, body)

assert checks["db"]["ok"] is True and checks["db"]["exists"] is True, checks["db"]
assert checks["schema"]["required_tables"]["slips"] is True, checks["schema"]
assert checks["schema"]["required_tables"]["ocr_jobs"] is True, checks["schema"]
assert checks["slips"]["total_count"] == 2, checks["slips"]
assert checks["slips"]["success_nonduplicate_count"] == 1, checks["slips"]
assert checks["slips"]["success_nonduplicate_amount"] == 150.25, checks["slips"]
assert checks["ocr_queue"]["counts"] == {"failed": 1, "processing": 1, "queued": 1}, checks["ocr_queue"]
assert checks["ocr_queue"]["active_count"] == 2, checks["ocr_queue"]
assert checks["ocr_queue"]["stale_active_count"] == 1, checks["ocr_queue"]
assert checks["pending_actions"]["pending_count"] == 1, checks["pending_actions"]
assert checks["watchdog"]["state_file"]["exists"] is True, checks["watchdog"]
assert 0 <= checks["watchdog"]["state_file"]["age_seconds"] <= 180, checks["watchdog"]

rendered = json.dumps(body, ensure_ascii=False)
assert str(DB_PATH) not in rendered, "health leaked absolute DB path"
assert "TEST_TOKEN" not in rendered and "SHOULD_NOT_LEAK" not in rendered, "health leaked secret-like data"
assert "1234567890" not in rendered, "health leaked pending action payload/account number"

print("ok: /api/health reports read-only operational checks without sensitive data")
