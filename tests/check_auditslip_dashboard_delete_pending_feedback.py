#!/usr/bin/env python3
"""Guard: source-bank-review delete requests hide the card from the review queue.

When an operator clicks a red delete button on a source-bank-review card, Phase B
governance still creates a pending two-person approval before the slip is actually
soft-deleted. But the card should disappear from the recheck queue immediately
while the delete is pending, so switching dates or waiting for refresh does not
make an already-requested item look like it came back.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot3:BOT_TOKEN:บริษัท 3"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-delete-pending-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-delete-pending-export-")))
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
    "id": "SLIP_REVIEW_DELETE",
    "bot_key": "bot3",
    "company_name": "บริษัท 3",
    "chat_id": "CHAT_TOPUP",
    "chat_title": "333 สลิป (เติมมือ)",
    "message_id": 4814,
    "file_id": "FILE_REVIEW_DELETE",
    "sender_name": "Admin 5",
    "username": "admin5",
    "status": "success",
    "slip_date_display": "23/05/26",
    "slip_date_iso": "2026-05-23",
    "slip_time": "19:16",
    "transferor_name": "",
    "recipient_name": "บริษัท 3",
    "issuer_bank": "",
    "from_bank": "",
    "from_account": "",
    "to_bank": "",
    "to_account": "",
    "amount": 3.0,
    "reference_no": "REF-4814",
})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

before = Dash.dashboard_snapshot(db_path, bot_key="bot3", scope="2026-05-23", flow_type="deposit")
assert before["totals"]["source_bank_review_count"] == 1, before["totals"]
assert [r["id"] for r in before["source_bank_review"]] == ["SLIP_REVIEW_DELETE"], before["source_bank_review"]

payload = {"id": "SLIP_REVIEW_DELETE", "bot_key": "bot3", "reason": "dashboard operator delete"}
first_request = Dash.request_pending_action_once(
    db_path,
    action="slip.delete",
    payload=payload,
    requested_by="actor-requester",
    request_id="req-delete-1",
)
assert first_request["ok"] is True and first_request["status"] == "pending", first_request
assert first_request["already_pending"] is False, first_request

# Requesting the same slip.delete again should reuse the existing pending row, not spam duplicates.
second_request = Dash.request_pending_action_once(
    db_path,
    action="slip.delete",
    payload=payload,
    requested_by="actor-requester",
    request_id="req-delete-2",
)
assert second_request["ok"] is True and second_request["status"] == "pending", second_request
assert second_request["already_pending"] is True, second_request
assert second_request["pending_id"] == first_request["pending_id"], (first_request, second_request)
with sqlite3.connect(db_path) as conn:
    pending_count = conn.execute("SELECT COUNT(*) FROM pending_actions WHERE action='slip.delete' AND status='pending'").fetchone()[0]
    slip_status = conn.execute("SELECT status FROM slips WHERE id='SLIP_REVIEW_DELETE'").fetchone()[0]
assert pending_count == 1, pending_count
assert slip_status == "success", slip_status

# Pending request hides it from the recheck queue, even though the slip is not
# actually soft-deleted until approval/execution.
after_request = Dash.dashboard_snapshot(db_path, bot_key="bot3", scope="2026-05-23", flow_type="deposit")
assert after_request["totals"]["source_bank_review_count"] == 0, after_request["totals"]
assert after_request["source_bank_review"] == [], after_request["source_bank_review"]

# After a second person approves and execution runs, soft-delete removes it from review/totals.
approved = Dash.approve_pending_action(db_path, first_request["pending_id"], "actor-approver")
assert approved.get("ok") is True, approved
result = Dash.delete_dashboard_slip(db_path, "SLIP_REVIEW_DELETE", "bot3", "dashboard operator delete")
assert result.get("ok") is True, result
Dash.mark_pending_executed(db_path, first_request["pending_id"], executed_result=str(result.get("previous_status") or ""))
after_execute = Dash.dashboard_snapshot(db_path, bot_key="bot3", scope="2026-05-23", flow_type="deposit")
assert after_execute["totals"]["source_bank_review_count"] == 0, after_execute["totals"]
assert after_execute["source_bank_review"] == [], after_execute["source_bank_review"]

html = Dash.render_dashboard_html("test-token")
scripts = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
assert "ขอลบรายการนี้" in html, "button copy must say request-delete, not immediate delete"
assert "approval:'request'" in scripts, "delete button should explicitly request approval"
assert "data.status === 'pending'" in scripts, "pending response must be handled separately"
assert "ส่งคำขอลบแล้ว" in scripts and "รออนุมัติ" in scripts, "pending UX must explain approval state"
assert "await load({scrollTop:false});" in scripts, "pending approve/execute/reject/cancel must refresh dashboard detail panels"
assert "already_pending" in scripts, "duplicate taps should be explained as existing pending request"

print("ok: delete request hides source-bank-review card while approval stays pending")
