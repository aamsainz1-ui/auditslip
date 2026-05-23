#!/usr/bin/env python3
"""Guard: dashboard summary defaults/filters can show today and date-range split totals."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TOKEN_RANGE"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botr:BOT_TOKEN:บริษัท Range"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-today-range-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-today-range-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TOKEN_RANGE", db_path=db_path, dry_run=True, bot_key="botr", company_name="บริษัท Range")
bot.init_db()

today_iso = bot_mod.bkk_now().strftime("%Y-%m-%d")
today_display = datetime.strptime(today_iso, "%Y-%m-%d").strftime("%d/%m/%y")
yesterday_iso = (datetime.strptime(today_iso, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
yesterday_display = datetime.strptime(yesterday_iso, "%Y-%m-%d").strftime("%d/%m/%y")
old_iso = (datetime.strptime(today_iso, "%Y-%m-%d") - timedelta(days=2)).strftime("%Y-%m-%d")
old_display = datetime.strptime(old_iso, "%Y-%m-%d").strftime("%d/%m/%y")

base = {
    "bot_key": "botr",
    "company_name": "บริษัท Range",
    "sender_name": "Uploader",
    "status": "success",
    "slip_time": "10:00",
    "transferor_name": "ลูกค้า",
    "recipient_name": "บริษัท Range",
    "from_bank": "KBANK",
    "to_bank": "SCB",
    "reference_no": "REF-BASE",
}

bot.save_slip({**base, "id": "TODAY_WD", "chat_id": "CHAT_WITHDRAW", "chat_title": "บริษัท Range ถอน", "message_id": 11, "file_id": "FILE_TODAY_WD", "amount": 1000.0, "slip_date_display": today_display, "slip_date_iso": today_iso, "reference_no": "REF-TODAY-WD"})
bot.save_slip({**base, "id": "TODAY_DEP", "chat_id": "CHAT_DEPOSIT", "chat_title": "บริษัท Range ฝาก", "message_id": 12, "file_id": "FILE_TODAY_DEP", "amount": 300.0, "slip_date_display": today_display, "slip_date_iso": today_iso, "reference_no": "REF-TODAY-DEP"})
bot.save_slip({**base, "id": "YDAY_WD", "chat_id": "CHAT_WITHDRAW", "chat_title": "บริษัท Range ถอน", "message_id": 21, "file_id": "FILE_YDAY_WD", "amount": 2000.0, "slip_date_display": yesterday_display, "slip_date_iso": yesterday_iso, "reference_no": "REF-YDAY-WD"})
bot.save_slip({**base, "id": "OLD_DEP", "chat_id": "CHAT_DEPOSIT", "chat_title": "บริษัท Range ฝาก", "message_id": 31, "file_id": "FILE_OLD_DEP", "amount": 900.0, "slip_date_display": old_display, "slip_date_iso": old_iso, "reference_no": "REF-OLD-DEP"})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snap_today = Dash.dashboard_snapshot(db_path, bot_key="botr", flow_type="all", scope="today")
assert snap_today["scope_label"] == "วันนี้", snap_today
assert snap_today["totals"]["selected_success_count"] == 2, snap_today["totals"]
assert snap_today["totals"]["selected_success_amount"] == 1300.0, snap_today["totals"]
assert snap_today["totals"]["withdraw_limit_count"] == 1, snap_today["totals"]
assert snap_today["totals"]["withdraw_limit_amount"] == 1000.0, snap_today["totals"]
assert snap_today["totals"]["deposit_customer_count"] == 1, snap_today["totals"]
assert snap_today["totals"]["deposit_customer_amount"] == 300.0, snap_today["totals"]

snap_range = Dash.dashboard_snapshot(db_path, bot_key="botr", flow_type="all", scope=f"range:{yesterday_iso}..{today_iso}")
assert snap_range["totals"]["selected_success_count"] == 3, snap_range["totals"]
assert snap_range["totals"]["selected_success_amount"] == 3300.0, snap_range["totals"]
assert snap_range["totals"]["withdraw_limit_amount"] == 3000.0, snap_range["totals"]
assert snap_range["totals"]["deposit_customer_amount"] == 300.0, snap_range["totals"]
assert old_iso not in {row["slip_date_iso"] for row in snap_range["recent"]}, snap_range["recent"]

html = Dash.render_dashboard_html("test-token")
for marker in [
    'option value="today" selected',
    "summaryStartDate",
    "summaryEndDate",
    "range:${summaryStart}..${summaryEnd}",
    "ยอดถอนวันนี้/ช่วงที่เลือก",
    "ยอดฝาก/เติมมือวันนี้/ช่วงที่เลือก",
]:
    assert marker in html, marker

print("ok: dashboard top split totals can show today-only and selected date ranges")
