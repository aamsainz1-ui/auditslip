#!/usr/bin/env python3
"""Guard: destructive operations (slip delete) require two-person approval.

actor_A requests → pending row created, slip not deleted.
actor_A cannot approve own request (self-approval rejected).
actor_B approves → status='approved'.
delete_dashboard_slip runs only after approval; pending row becomes 'executed'.
"""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot3:BOT_TOKEN:บริษัท 3"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-approval-flow-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-approval-flow-export-")))
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
bot.save_slip({
    "id": "SLIP_TO_DELETE",
    "bot_key": "bot3",
    "company_name": "บริษัท 3",
    "chat_id": "CHAT_DEPOSIT",
    "chat_title": "บริษัท 3 เติม",
    "message_id": 11,
    "file_id": "FILE_DEL",
    "sender_name": "Alice",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:00",
    "transferor_name": "ลูกค้า",
    "recipient_name": "บริษัท 3",
    "from_account": "1234567890",
    "to_account": "0987654321",
    "amount": 500.0,
    "reference_no": "REF-DEL",
})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

actor_a = "fpAAAAAAAAAA"
actor_b = "fpBBBBBBBBBB"

# Step 1: actor_A requests slip delete -> pending row, slip untouched
payload = {"id": "SLIP_TO_DELETE", "slip_id": "SLIP_TO_DELETE", "bot_key": "bot3", "reason": "operator delete"}
pending_id = Dash.create_pending_action(db_path, action="slip.delete", payload=payload, requested_by=actor_a, request_id="req-AAA")
assert isinstance(pending_id, int) and pending_id > 0, pending_id

with sqlite3.connect(db_path) as conn:
    row = conn.execute("SELECT status FROM slips WHERE id=?", ("SLIP_TO_DELETE",)).fetchone()
assert row == ("success",), f"slip must not yet be deleted, got {row}"

loaded = Dash.load_pending_action(db_path, pending_id)
assert loaded["status"] == "pending", loaded
assert loaded["requested_by"] == actor_a, loaded
assert loaded["action"] == "slip.delete", loaded

# Step 2: actor_A tries to approve own request -> self-approval rejected
self_approve = Dash.approve_pending_action(db_path, pending_id, actor_a)
assert self_approve.get("ok") is False, self_approve
assert "self-approval" in (self_approve.get("error") or ""), self_approve
# Pending stays 'pending'
assert Dash.load_pending_action(db_path, pending_id)["status"] == "pending"

# Step 3: actor_B approves -> status='approved'
ok_approve = Dash.approve_pending_action(db_path, pending_id, actor_b)
assert ok_approve.get("ok") is True, ok_approve
loaded = Dash.load_pending_action(db_path, pending_id)
assert loaded["status"] == "approved", loaded
assert loaded["approved_by"] == actor_b, loaded
assert loaded["approved_at"], loaded

# Cannot approve twice
double_approve = Dash.approve_pending_action(db_path, pending_id, actor_b)
assert double_approve.get("ok") is False, double_approve

# Step 4: Execute via stored payload path
stored_payload = Dash.pending_action_payload(loaded)
result = Dash.delete_dashboard_slip(
    db_path,
    str(stored_payload.get("id") or ""),
    str(stored_payload.get("bot_key") or ""),
    str(stored_payload.get("reason") or "dashboard operator delete"),
)
assert result.get("ok") is True, result
Dash.mark_pending_executed(db_path, pending_id, executed_result=str(result.get("previous_status") or ""))

with sqlite3.connect(db_path) as conn:
    row = conn.execute("SELECT status FROM slips WHERE id=?", ("SLIP_TO_DELETE",)).fetchone()
assert row == ("deleted",), f"slip should now be deleted, got {row}"

executed_row = Dash.load_pending_action(db_path, pending_id)
assert executed_row["status"] == "executed", executed_row
assert executed_row["executed_at"], executed_row

# Cannot re-execute (status is no longer 'approved')
double_exec = Dash.approve_pending_action(db_path, pending_id, actor_b)
assert double_exec.get("ok") is False, double_exec

# /api/pending listing returns the executed row with PII-light summary
listed = Dash.list_pending_actions(db_path)
assert any(r["id"] == pending_id and r["status"] == "executed" for r in listed), listed
match = [r for r in listed if r["id"] == pending_id][0]
assert "payload_json" not in match, "payload_json must not leak in listing"
assert "payload_summary" in match, match
assert match["payload_summary"].get("id") == "SLIP_TO_DELETE", match["payload_summary"]

# cancel_pending_action: requester-only path on a fresh pending
fresh_id = Dash.create_pending_action(db_path, action="slip.delete", payload={"id": "OTHER", "bot_key": "bot3"}, requested_by=actor_a, request_id="req-BBB")
cancel_other = Dash.cancel_pending_action(db_path, fresh_id, actor_b)
assert cancel_other.get("ok") is False, cancel_other
cancel_self = Dash.cancel_pending_action(db_path, fresh_id, actor_a)
assert cancel_self.get("ok") is True, cancel_self
assert Dash.load_pending_action(db_path, fresh_id)["status"] == "cancelled"

# reject_pending_action
reject_id = Dash.create_pending_action(db_path, action="slip.delete", payload={"id": "REJ", "bot_key": "bot3"}, requested_by=actor_a, request_id="req-CCC")
rejected = Dash.reject_pending_action(db_path, reject_id, actor_b, reason="not authorized")
assert rejected.get("ok") is True, rejected
assert Dash.load_pending_action(db_path, reject_id)["status"] == "rejected"

print("ok: two-person approval workflow enforces request/approve/execute with self-approval block")
