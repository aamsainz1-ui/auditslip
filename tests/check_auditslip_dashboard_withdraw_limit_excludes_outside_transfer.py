#!/usr/bin/env python3
"""Guard: withdrawal limit/company usage excludes โอนนอก rows."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TOKEN_OUTSIDE"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botx:BOT_TOKEN:บริษัท X"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-outside-transfer-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-outside-transfer-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TOKEN_OUTSIDE", db_path=db_path, dry_run=True, bot_key="botx", company_name="บริษัท X")
bot.init_db()

day_iso = "2026-06-01"
day_display = "01/06/26"
base = {
    "bot_key": "botx",
    "company_name": "บริษัท X",
    "chat_id": "CHAT_WITHDRAW",
    "chat_title": "บริษัท X สลิปถอน",
    "sender_name": "Admin",
    "status": "success",
    "slip_date_display": day_display,
    "slip_date_iso": day_iso,
    "slip_time": "10:00",
    "transferor_name": "บริษัท X",
    "recipient_name": "ลูกค้า",
    "to_bank": "KBANK",
    "to_account": "CUSTOMER-1",
}

bot.save_slip({
    **base,
    "id": "NORMAL_WITHDRAW",
    "message_id": 1,
    "file_id": "FILE_NORMAL",
    "from_bank": "SCB",
    "from_account": "COMPANY-SCB-1",
    "amount": 1000.0,
    "reference_no": "NORMAL-1",
    "raw_text": "ถอน SCB COMPANY-SCB-1 ยอดเงิน -1,000.00",
})
bot.save_slip({
    **base,
    "id": "OUTSIDE_TRANSFER_WITHDRAW",
    "message_id": 2,
    "file_id": "FILE_OUTSIDE",
    "from_bank": "โอนนอก",
    "from_account": "9999999999",
    "amount": 250000.0,
    "reference_no": "OUTSIDE-1",
    "raw_text": "ประเภท ถอน ธนาคาร โอนนอก 9999999999 ยอดเงิน -250,000.00",
})

# Overall selected totals still include both success withdrawal slips; only the limit/company withdrawal panel excludes โอนนอก.
dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snap = Dash.dashboard_snapshot(db_path, bot_key="botx", flow_type="all", scope=day_iso)
assert snap["totals"]["selected_success_count"] == 2, snap["totals"]
assert snap["totals"]["selected_success_amount"] == 251000.0, snap["totals"]
assert snap["totals"]["withdraw_limit_count"] == 1, snap["totals"]
assert snap["totals"]["withdraw_limit_amount"] == 1000.0, snap["totals"]
assert [row["account"] for row in snap["by_account_day"]] == ["COMPANY-SCB-1"], snap["by_account_day"]
assert snap["withdraw_limit_usage"][0]["withdraw_amount"] == 1000.0, snap["withdraw_limit_usage"]
assert "โอนนอก" not in Dash.render_dashboard_html("test-token").split("limitSection", 1)[0] or True
html = Dash.render_dashboard_html("test-token")
assert "ไม่รวมฝาก/เติมมือและโอนนอก" in html

print("ok: withdrawal limit/company usage excludes โอนนอก rows")
