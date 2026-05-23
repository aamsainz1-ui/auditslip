#!/usr/bin/env python3
"""Guard: operator/company overview cards must follow the selected day/range scope, not open-period totals."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TOKEN_SCOPE_RESET"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botscope:BOT_TOKEN:บริษัท Scope"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-company-scope-reset-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-company-scope-reset-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TOKEN_SCOPE_RESET", db_path=db_path, dry_run=True, bot_key="botscope", company_name="บริษัท Scope")
bot.init_db()

today_iso = bot_mod.bkk_now().strftime("%Y-%m-%d")
today_display = datetime.strptime(today_iso, "%Y-%m-%d").strftime("%d/%m/%y")
yesterday_iso = (datetime.strptime(today_iso, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
yesterday_display = datetime.strptime(yesterday_iso, "%Y-%m-%d").strftime("%d/%m/%y")

base = {
    "bot_key": "botscope",
    "company_name": "บริษัท Scope",
    "sender_name": "Uploader",
    "status": "success",
    "slip_time": "10:00",
    "transferor_name": "ลูกค้า",
    "recipient_name": "บริษัท Scope",
    "from_bank": "KBANK",
    "to_bank": "SCB",
}

# Old/open withdrawal rows must not leak into the mobile "งานวันนี้" company cards after midnight.
bot.save_slip({**base, "id": "YDAY_WD", "chat_id": "CHAT_WITHDRAW", "chat_title": "บริษัท Scope ถอน", "message_id": 21, "file_id": "FILE_YDAY_WD", "amount": 5000.0, "slip_date_display": yesterday_display, "slip_date_iso": yesterday_iso, "reference_no": "REF-YDAY-WD"})
bot.save_slip({**base, "id": "YDAY_DUP", "chat_id": "CHAT_WITHDRAW", "chat_title": "บริษัท Scope ถอน", "message_id": 22, "file_id": "FILE_YDAY_DUP", "amount": 900.0, "slip_date_display": yesterday_display, "slip_date_iso": yesterday_iso, "reference_no": "REF-YDAY-DUP", "is_duplicate": 1, "duplicate_of": "YDAY_WD"})

# Only this deposit belongs to today's operator overview.
bot.save_slip({**base, "id": "TODAY_DEP", "chat_id": "CHAT_DEPOSIT", "chat_title": "บริษัท Scope ฝาก", "message_id": 31, "file_id": "FILE_TODAY_DEP", "amount": 300.0, "slip_date_display": today_display, "slip_date_iso": today_iso, "reference_no": "REF-TODAY-DEP"})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snap_today = Dash.dashboard_snapshot(db_path, bot_key="__all__", flow_type="all", scope="today")
assert snap_today["scope_label"] == "วันนี้", snap_today
company_rows = [row for row in snap_today["company_summary"] if row.get("bot_key") == "botscope"]
assert len(company_rows) == 1, snap_today["company_summary"]
row = company_rows[0]

assert row["withdraw_open_count"] == 0, row
assert row["withdraw_open_amount"] == 0.0, row
assert row["deposit_open_count"] == 1, row
assert row["deposit_open_amount"] == 300.0, row
assert row["open_count"] == 1, row
assert row["open_amount"] == 300.0, row
assert row["duplicate_count"] == 0, row

snap_yesterday = Dash.dashboard_snapshot(db_path, bot_key="__all__", flow_type="all", scope=yesterday_iso)
yday_row = [row for row in snap_yesterday["company_summary"] if row.get("bot_key") == "botscope"][0]
assert yday_row["withdraw_open_count"] == 1, yday_row
assert yday_row["withdraw_open_amount"] == 5000.0, yday_row
assert yday_row["duplicate_count"] == 1, yday_row

print("ok: company/operator overview cards follow selected day scope and reset after midnight")
