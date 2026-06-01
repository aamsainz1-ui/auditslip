#!/usr/bin/env python3
"""Guard: withdrawal limit/company usage excludes โอนนอก rows but reports them separately."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TOKEN_OUTSIDE_X"
os.environ["BOT_TOKEN_Y"] = "TOKEN_OUTSIDE_Y"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botx:BOT_TOKEN:บริษัท X,boty:BOT_TOKEN_Y:บริษัท Y"
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
bot_x = bot_mod.AuditslipBot(token="TOKEN_OUTSIDE_X", db_path=db_path, dry_run=True, bot_key="botx", company_name="บริษัท X")
bot_y = bot_mod.AuditslipBot(token="TOKEN_OUTSIDE_Y", db_path=db_path, dry_run=True, bot_key="boty", company_name="บริษัท Y")
bot_x.init_db()
bot_y.init_db()

day_iso = "2026-06-01"
day_display = "01/06/26"
base = {
    "chat_id": "CHAT_WITHDRAW",
    "chat_title": "สลิปถอน",
    "sender_name": "Admin",
    "status": "success",
    "slip_date_display": day_display,
    "slip_date_iso": day_iso,
    "slip_time": "10:00",
    "recipient_name": "ลูกค้า",
    "to_bank": "KBANK",
    "to_account": "CUSTOMER-1",
}

bot_x.save_slip({
    **base,
    "id": "NORMAL_WITHDRAW",
    "bot_key": "botx",
    "company_name": "บริษัท X",
    "message_id": 1,
    "file_id": "FILE_NORMAL",
    "transferor_name": "บริษัท X",
    "from_bank": "SCB",
    "from_account": "COMPANY-SCB-1",
    "amount": 1000.0,
    "reference_no": "NORMAL-1",
    "raw_text": "ถอน SCB COMPANY-SCB-1 ยอดเงิน -1,000.00",
})
bot_x.save_slip({
    **base,
    "id": "OUTSIDE_TRANSFER_WITHDRAW_X",
    "bot_key": "botx",
    "company_name": "บริษัท X",
    "message_id": 2,
    "file_id": "FILE_OUTSIDE_X",
    "transferor_name": "บริษัท X",
    "from_bank": "โอนนอก",
    "from_account": "9999999999",
    "amount": 250000.0,
    "reference_no": "OUTSIDE-X",
    "raw_text": "ประเภท ถอน ธนาคาร โอนนอก 9999999999 ยอดเงิน -250,000.00",
})
bot_y.save_slip({
    **base,
    "id": "OUTSIDE_TRANSFER_WITHDRAW_Y",
    "bot_key": "boty",
    "company_name": "บริษัท Y",
    "message_id": 3,
    "file_id": "FILE_OUTSIDE_Y",
    "transferor_name": "บริษัท Y",
    "from_bank": "",
    "from_account": "2222222222",
    "to_bank": "EXTERNAL TRANSFER",
    "amount": 50000.0,
    "reference_no": "OUTSIDE-Y",
    "raw_text": "ประเภท ถอน ธนาคาร external transfer 2222222222 ยอดเงิน -50,000.00",
})

# Overall selected totals still include all success withdrawal slips; only the limit/company withdrawal panel excludes โอนนอก.
dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snap = Dash.dashboard_snapshot(db_path, bot_key="__all__", flow_type="all", scope=day_iso)
assert snap["totals"]["selected_success_count"] == 3, snap["totals"]
assert snap["totals"]["selected_success_amount"] == 301000.0, snap["totals"]
assert snap["totals"]["withdraw_limit_count"] == 1, snap["totals"]
assert snap["totals"]["withdraw_limit_amount"] == 1000.0, snap["totals"]
assert snap["totals"]["outside_transfer_count"] == 2, snap["totals"]
assert snap["totals"]["outside_transfer_amount"] == 300000.0, snap["totals"]
assert [row["account"] for row in snap["by_account_day"]] == ["COMPANY-SCB-1"], snap["by_account_day"]
assert snap["withdraw_limit_usage"][0]["withdraw_amount"] == 1000.0, snap["withdraw_limit_usage"]
outside = {row["company_name"]: row for row in snap["outside_transfer_withdrawals"]}
assert set(outside) == {"บริษัท X", "บริษัท Y"}, snap["outside_transfer_withdrawals"]
assert outside["บริษัท X"]["amount"] == 250000.0 and outside["บริษัท X"]["count"] == 1, outside
assert outside["บริษัท Y"]["amount"] == 50000.0 and outside["บริษัท Y"]["count"] == 1, outside
assert outside["บริษัท X"]["rows"][0]["message_id"] == 2, outside
assert outside["บริษัท Y"]["rows"][0]["message_id"] == 3, outside

html = Dash.render_dashboard_html("test-token")
for marker in [
    "ไม่รวมฝาก/เติมมือและโอนนอก",
    "ถอนโอนนอก · แยกต่างหาก",
    "outsideTransferWithdrawals",
    "renderOutsideTransferWithdrawals",
    "รายการในบริษัทนี้",
]:
    assert marker in html, marker

lite = Dash.dashboard_snapshot(db_path, bot_key="__all__", flow_type="all", scope=day_iso, detail_level="lite")
assert lite["totals"]["outside_transfer_amount"] == 300000.0, lite["totals"]
assert lite["outside_transfer_withdrawals"] == [], lite["outside_transfer_withdrawals"]

print("ok: withdrawal limit/company usage excludes โอนนอก and reports it separately per company")
