#!/usr/bin/env python3
"""Guard: dashboard reconciliation uses selected bot/flow/chat scope and displays operator-ready details."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A,botB:BOT_TOKEN:บริษัท B"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-reconcile-scope-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-reconcile-scope-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot_a = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="botA", company_name="บริษัท A")
bot_a.init_db()
bot_b = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="botB", company_name="บริษัท B")
bot_b.init_db()

base = {
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:11",
    "transferor_name": "ลูกค้า A",
    "recipient_name": "บริษัท",
    "from_bank": "SCB",
    "to_bank": "KBANK",
    "amount": 100.0,
}

bot_a.save_slip({**base, "bot_key": "botA", "company_name": "บริษัท A", "id": "A_DEP", "chat_id": "CHAT_A_DEP", "chat_title": "บริษัท A เติมมือ", "message_id": 1, "file_id": "FILE_A_DEP", "amount": 98.0, "reference_no": "ADEP98"})
bot_a.save_slip({**base, "bot_key": "botA", "company_name": "บริษัท A", "id": "A_WD", "chat_id": "CHAT_A_WD", "chat_title": "บริษัท A ถอน", "message_id": 2, "file_id": "FILE_A_WD", "amount": 150.0, "reference_no": "AWD150"})
bot_b.save_slip({**base, "bot_key": "botB", "company_name": "บริษัท B", "id": "B_DEP", "chat_id": "CHAT_B_DEP", "chat_title": "บริษัท B ฝาก", "message_id": 3, "file_id": "FILE_B_DEP", "amount": 98.0, "reference_no": "BDEP98"})

xlsx = Path(tempfile.mkdtemp(prefix="auditslip-reconcile-transactions-")) / "transactions.xlsx"
wb = Workbook()
ws = wb.active
assert ws is not None
ws.title = "Transactions"
ws.append(["วันที่", "เวลา", "ยูสเซอร์", "ธนาคาร", "จำนวน", "จำนวนที่ได้รับ", "รหัส", "หมายเหตุ", "ไฟล์/แหล่งที่มา"])
ws.append(["22/05/26", "10:11", "ลูกค้า A", "SCB", 100.0, 98.0, "ADEP98", "เติมมือ", "transactions.xlsx"])
wb.save(xlsx)

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

backend_rows = Dash.parse_backend_excel(xlsx)
assert backend_rows[0]["amount"] == 98.0, backend_rows
assert backend_rows[0]["time"] == "10:11", backend_rows
assert backend_rows[0]["source"] == "transactions.xlsx", backend_rows

# Company + flow scope must reconcile only botA deposit, not botA withdraw or botB deposit.
result = Dash.reconcile_backend_excel(db_path, xlsx, chat_id="", bot_key="botA", flow_type="deposit", scope="all")
assert result["ok"] is True, result
assert result["scope"]["bot_key"] == "botA" and result["scope"]["flow_type"] == "deposit", result
assert result["backend"]["count"] == 1, result
assert result["slips"]["count"] == 1 and result["slips"]["amount"] == 98.0, result
assert result["matched"]["count"] == 1 and result["missing"]["count"] == 0 and result["extra"]["count"] == 0, result
assert result["daily"]["backend"][0]["date"] == "22/05/26" and result["daily"]["backend"][0]["amount"] == 98.0, result
assert result["matched"]["rows"][0]["backend"]["time"] == "10:11", result

withdraw_result = Dash.reconcile_backend_excel(db_path, xlsx, chat_id="", bot_key="botA", flow_type="withdraw", scope="all")
assert withdraw_result["slips"]["count"] == 1 and withdraw_result["extra"]["count"] == 1, withdraw_result
assert withdraw_result["missing"]["count"] == 1, withdraw_result

html = Dash.render_dashboard_html("test-token")
source_text = (ROOT / "auditslip_dashboard.py").read_text(encoding="utf-8")
for marker in [
    "const parts = selectedChatParts();",
    "bot_key",
    "flow_type",
    "form.append('bot_key'",
    "form.append('flow_type'",
    "ผลเทียบยอด: ครบ",
    "หลังบ้านมี แต่ไม่พบในสลิป",
    "สลิปมี แต่ไม่พบในหลังบ้าน",
    "รายการที่ตรงกัน",
    "สรุปรายวัน",
    "reconcile_scope",
]:
    assert marker in html, marker
for marker in [
    '"flow_type"',
    "bot_key = str(payload.get(\"bot_key\")",
    "flow_type = str(payload.get(\"flow_type\")",
    "reconcile_backend_excel(DB_PATH, excel_path, chat_id=chat_id, scope=scope, bot_key=bot_key, flow_type=flow_type)",
]:
    assert marker in source_text, marker

print("ok: reconcile dashboard scopes selected bot/flow/chat and displays detailed status")
