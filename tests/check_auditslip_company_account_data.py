#!/usr/bin/env python3
"""Guard: dashboard manages company/account-number master data for Auditslip."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-company-accounts-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-company-accounts-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True, bot_key="bot1", company_name="บริษัท 1")
bot.init_db()
bot.save_slip({
    "id": "ACC_SLIP_1",
    "bot_key": "bot1",
    "company_name": "บริษัท 1",
    "chat_id": "CHAT1",
    "chat_title": "ห้องบริษัท 1",
    "message_id": 11,
    "file_id": "FILE11",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:11",
    "transferor_name": "คุณลูกค้า",
    "recipient_name": "บริษัท 1",
    "to_bank": "SCB",
    "to_account": "222-333-4444",
    "account_name": "บจก. บริษัท 1",
    "amount": 1500.0,
    "confidence": 0.99,
})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

saved = Dash.save_company_account(
    Path(os.environ["AUDITSLIP_DB"]),
    bot_key="bot1",
    chat_id="CHAT1",
    company_name="บริษัท 1",
    bank="ไทยพาณิชย์",
    account_no="222-333-4444",
    account_name="บจก. บริษัท 1",
    daily_limit=500000.0,
)
assert saved["ok"] is True, saved
assert saved["bank"] == "SCB", saved
assert saved["company_name"] == "บริษัท 1", saved

snapshot = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]), chat_id="CHAT1", bot_key="bot1", scope="open")
accounts = snapshot["company_accounts"]
assert len(accounts) == 1, accounts
assert accounts[0]["company_name"] == "บริษัท 1", accounts
assert accounts[0]["account_name"] == "บจก. บริษัท 1", accounts
assert accounts[0]["account_no"] == "222-333-4444", accounts
assert accounts[0]["bank"] == "SCB", accounts
assert accounts[0]["daily_limit"] == 500000.0, accounts
assert snapshot["chats"][0]["bot_key"] == "bot1", snapshot["chats"]
assert snapshot["selected_bot_key"] == "bot1", snapshot

html = Dash.render_dashboard_html("test-token")
for marker in ["companyAccounts", "บริษัทย่อย/บัญชีรับเงิน", "accountName", "accountNo", "companyName", "saveCompanyAccount"]:
    assert marker in html, marker

print("ok: company account master data")
