#!/usr/bin/env python3
"""Guard: pending approval rows whose expires_at is in the past become 'expired',
and an approve attempt afterwards is rejected with HTTP 409 status."""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot3:BOT_TOKEN:บริษัท 3"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-approval-expiry-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-approval-expiry-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="bot3", company_name="บริษัท 3")
bot.init_db()

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

actor_a = "fpAAAAAAAAAA"
actor_b = "fpBBBBBBBBBB"

# Create a pending row, then hand-edit expires_at to be in the past
pid = Dash.create_pending_action(db_path, action="slip.delete", payload={"id": "X", "bot_key": "bot3"}, requested_by=actor_a, request_id="req-EXP")
past_iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()
with sqlite3.connect(db_path) as conn:
    conn.execute("UPDATE pending_actions SET expires_at=? WHERE id=?", (past_iso, pid))
    conn.commit()

# Sanity: row is still 'pending' until expire job runs
row = Dash.load_pending_action(db_path, pid)
assert row["status"] == "pending", row

# Run expiry job
expired_count = Dash.expire_old_pending_actions(db_path)
assert expired_count >= 1, expired_count
row = Dash.load_pending_action(db_path, pid)
assert row["status"] == "expired", row

# Approve attempt on expired row -> rejected with status 409
result = Dash.approve_pending_action(db_path, pid, actor_b)
assert result.get("ok") is False, result
assert result.get("status") == 409, result
assert "expired" in (result.get("error") or "").lower() or "cannot approve" in (result.get("error") or "").lower(), result

# A fresh pending row (not yet expired) should still expire properly only if past
fresh = Dash.create_pending_action(db_path, action="slip.delete", payload={"id": "Y", "bot_key": "bot3"}, requested_by=actor_a, request_id="req-EXP2")
not_expired = Dash.expire_old_pending_actions(db_path)
# Should not flip the fresh one
assert Dash.load_pending_action(db_path, fresh)["status"] == "pending", "fresh row must not be expired"

# Cancel on expired -> 409 too
cancel_expired = Dash.cancel_pending_action(db_path, pid, actor_a)
assert cancel_expired.get("ok") is False, cancel_expired
assert cancel_expired.get("status") == 409, cancel_expired

print("ok: pending actions expire after TTL and reject post-expiry approve/cancel")
