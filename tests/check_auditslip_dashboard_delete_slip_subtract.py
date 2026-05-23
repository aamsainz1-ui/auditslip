#!/usr/bin/env python3
"""Guard: dashboard delete removes a slip from visible lists and subtracts its amount from totals."""
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
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-delete-slip-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-delete-slip-export-")))
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
base = {
    "bot_key": "bot3",
    "company_name": "บริษัท 3",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:00",
    "transferor_name": "ลูกค้า",
    "recipient_name": "บริษัท 3",
    "from_account": "1234567890",
    "to_account": "0987654321",
    "amount": 100.0,
    "reference_no": "REF-BASE",
}
bot.save_slip({**base, "id": "DEP_REVIEW", "chat_id": "CHAT_DEPOSIT", "chat_title": "บริษัท 3 เติมมือ", "message_id": 21, "file_id": "FILE_DEP", "from_bank": "", "to_bank": "", "amount": 300.0, "reference_no": "REF-DEP"})
bot.save_slip({**base, "id": "WD_KEEP", "chat_id": "CHAT_WITHDRAW", "chat_title": "บริษัท 3 ถอน", "message_id": 31, "file_id": "FILE_WD", "from_bank": "SCB", "to_bank": "KBANK", "amount": 1000.0, "reference_no": "REF-WD"})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

before = Dash.dashboard_snapshot(db_path, bot_key="bot3", flow_type="deposit", scope="open")
assert before["totals"]["selected_success_count"] == 1, before["totals"]
assert before["totals"]["selected_success_amount"] == 300.0, before["totals"]
assert [r["id"] for r in before["source_bank_review"]] == ["DEP_REVIEW"], before["source_bank_review"]
assert [r["id"] for r in before["recent"]] == ["DEP_REVIEW"], before["recent"]

result = Dash.delete_dashboard_slip(db_path, "DEP_REVIEW", "bot3")
assert result["ok"] is True, result
assert result["removed_amount"] == 300.0, result
assert result["was_counted"] is True, result

after_dep = Dash.dashboard_snapshot(db_path, bot_key="bot3", flow_type="deposit", scope="open")
assert after_dep["totals"]["selected_success_count"] == 0, after_dep["totals"]
assert after_dep["totals"]["selected_success_amount"] == 0.0, after_dep["totals"]
assert after_dep["source_bank_review"] == [], after_dep["source_bank_review"]
assert "DEP_REVIEW" not in [r["id"] for r in after_dep["recent"]], after_dep["recent"]

with sqlite3.connect(db_path) as conn:
    row = conn.execute("SELECT status, amount FROM slips WHERE id='DEP_REVIEW'").fetchone()
assert row == ("deleted", 300.0), row

after_wd = Dash.dashboard_snapshot(db_path, bot_key="bot3", flow_type="withdraw", scope="open")
assert after_wd["totals"]["selected_success_count"] == 1, after_wd["totals"]
assert after_wd["totals"]["selected_success_amount"] == 1000.0, after_wd["totals"]
assert [r["id"] for r in after_wd["recent"]] == ["WD_KEEP"], after_wd["recent"]

html = Dash.render_dashboard_html("test-token")
for marker in ["deleteSlip", "/api/slip/delete", "data-delete-slip-id", "ลบรายการนี้", "หักยอดออก"]:
    assert marker in html, marker

print("ok: dashboard delete subtracts slip amount and hides deleted rows")
