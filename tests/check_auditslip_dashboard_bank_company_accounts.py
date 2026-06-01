#!/usr/bin/env python3
"""Guard: bank section lists company deposit/withdraw accounts, not customer accounts."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TOKEN_BANK_ACCOUNTS"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot1:BOT_TOKEN:บริษัท 1"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-bank-company-accounts-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-bank-company-accounts-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TOKEN_BANK_ACCOUNTS", db_path=db_path, dry_run=True, bot_key="bot1", company_name="บริษัท 1")
bot.init_db()

base = {
    "bot_key": "bot1",
    "company_name": "บริษัท 1",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "01/06/26",
    "slip_date_iso": "2026-06-01",
    "slip_time": "10:00",
    "amount": 100.0,
}

# Deposit/top-up: customer transfers to company.  The bank section must list
# the recipient/destination company account, not the customer transferor.
bot.save_slip({
    **base,
    "id": "DEP1",
    "chat_id": "CHAT_DEPOSIT",
    "chat_title": "111 สลิป (เติมมือ)",
    "message_id": 101,
    "file_id": "FILE_DEP1",
    "transferor_name": "ลูกค้าฝาก ห้ามแสดง",
    "recipient_name": "บัญชีฝากบริษัท",
    "from_bank": "KBANK",
    "from_account": "111-ลูกค้า",
    "to_bank": "SCB",
    "to_account": "222-ฝากบริษัท",
    "reference_no": "DEP1",
})

# Withdraw: company transfers to customer.  The bank section must list the
# transferor/source company account, not the recipient/customer account.
bot.save_slip({
    **base,
    "id": "WD1",
    "chat_id": "CHAT_WITHDRAW",
    "chat_title": "111 สลิปถอน",
    "message_id": 201,
    "file_id": "FILE_WD1",
    "transferor_name": "บัญชีถอนบริษัท",
    "recipient_name": "ลูกค้าถอน ห้ามแสดง",
    "from_bank": "KRUNGTHAI",
    "from_account": "333-ถอนบริษัท",
    "to_bank": "TTB",
    "to_account": "444-ลูกค้า",
    "reference_no": "WD1",
})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snap = Dash.dashboard_snapshot(db_path, bot_key="bot1", flow_type="all", scope="2026-06-01")
rows = snap["bank_account_names"]
deposit_rows = [r for r in rows if r["flow_type"] == "deposit"]
withdraw_rows = [r for r in rows if r["flow_type"] == "withdraw"]

assert len(deposit_rows) == 1, rows
assert len(withdraw_rows) == 1, rows

dep = deposit_rows[0]
assert dep["account_name"] == "บัญชีฝากบริษัท", dep
assert dep["bank"] == "SCB", dep
assert dep["account"] == "222-ฝากบริษัท", dep
assert dep["account_role"] == "บัญชีฝาก/รับเงินของบริษัท", dep
assert "ลูกค้า" not in dep["account_name"], dep

wd = withdraw_rows[0]
assert wd["account_name"] == "บัญชีถอนบริษัท", wd
assert wd["bank"] == "KRUNGTHAI", wd
assert wd["account"] == "333-ถอนบริษัท", wd
assert wd["account_role"] == "บัญชีถอน/จ่ายของบริษัท", wd
assert "ลูกค้า" not in wd["account_name"], wd

html = Dash.render_dashboard_html("test-token")
for marker in [
    "บัญชีฝาก/รับเงินของบริษัท",
    "บัญชีถอน/จ่ายของบริษัท",
    'id="bankDepositAccountNames"',
    'id="bankWithdrawAccountNames"',
    "ไม่แสดงบัญชีลูกค้าผู้โอน",
    "ไม่แสดงบัญชีลูกค้าผู้รับเงิน",
]:
    assert marker in html, marker

print("ok: bank section lists company deposit/withdraw accounts, not customer accounts")
