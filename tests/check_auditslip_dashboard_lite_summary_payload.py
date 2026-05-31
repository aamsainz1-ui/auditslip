#!/usr/bin/env python3
"""Guard: dashboard auto-refresh can use a lite /api/summary payload.

Phase C payload diet: the polling snapshot must keep financial totals and company
navigation, but omit image-heavy/detail arrays so the 10s auto-refresh does not
re-download slip cards, duplicate images, review cards, or aggregate tables.
Manual/full loads still return the complete dashboard payload.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot1:BOT_TOKEN:บริษัท 1"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-lite-summary-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-lite-summary-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="bot1", company_name="บริษัท 1")
bot.init_db()
bot.save_slip({
    "id": "LITE-1",
    "bot_key": "bot1",
    "company_name": "บริษัท 1",
    "chat_id": "CHAT_WD",
    "chat_title": "บริษัท 1 ถอน",
    "message_id": 101,
    "file_id": "FILE_LITE_1",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "23/05/26",
    "slip_date_iso": "2026-05-23",
    "slip_time": "10:15",
    "transferor_name": "ลูกค้าทดสอบ",
    "recipient_name": "บริษัท 1",
    "from_bank": "SCB",
    "from_account": "111-222-333",
    "to_bank": "KBANK",
    "to_account": "999-888-777",
    "amount": 1234.0,
    "reference_no": "LITE101",
})

spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert spec and spec.loader
Dash = importlib.util.module_from_spec(spec)
sys.modules["auditslip_dashboard"] = Dash
spec.loader.exec_module(Dash)

full = Dash.dashboard_snapshot(db_path, bot_key="bot1", flow_type="withdraw", scope="2026-05-23")
assert full.get("detail_level", "full") == "full", full.keys()
assert full["totals"]["selected_success_count"] == 1, full["totals"]
assert full["company_summary"], full
assert full["chats"], full
assert full["recent"], full
assert full["company_account_daily"], full
assert full["by_account_day"], full

def _forbid_lite_detail_call(name):
    def _blocked(*args, **kwargs):
        raise AssertionError(f"lite snapshot should not compute detail helper: {name}")
    return _blocked

for helper_name in [
    "duplicate_pair_rows",
    "source_bank_review_rows",
    "account_slip_search_rows",
    "cross_company_account_usage",
    "cross_company_account_slip_search_rows",
    "date_totals",
    "daily_flow_totals",
    "bank_totals",
    "grouped_totals",
]:
    setattr(Dash, helper_name, _forbid_lite_detail_call(helper_name))

lite = Dash.dashboard_snapshot(db_path, bot_key="bot1", flow_type="withdraw", scope="2026-05-23", detail_level="lite")
assert lite["detail_level"] == "lite", lite.keys()
assert lite["totals"]["selected_success_count"] == 1, lite["totals"]
assert lite["company_summary"], lite
assert lite["company_menu"], lite
assert lite["chats"], lite
assert lite["exception_summary"]["total_count"] >= 0, lite["exception_summary"]

# Image/card/detail-heavy arrays must be empty in the polling payload.
for key in [
    "recent",
    "duplicate_pairs",
    "source_bank_review",
    "deposit_customer_slips",
    "issues",
    "jobs_recent",
    "provider_usage",
    "company_account_daily",
    "account_cross_company",
    "by_transferor",
    "by_account_day",
    "by_date",
    "daily_flow_summary",
    "by_from_bank",
    "by_to_bank",
    "by_sender",
]:
    assert lite[key] == [], (key, lite[key])
assert lite["account_slip_search"]["rows"] == [], lite["account_slip_search"]
assert lite["cross_company_account_slip_search"]["rows"] == [], lite["cross_company_account_slip_search"]
assert "image_url" not in str(lite), lite

html = Dash.render_dashboard_html("test-token")
scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
assert scripts, "dashboard script missing"
script_text = "\n".join(scripts)
assert "const detailLevel = (options && options.lite) ? 'lite' : 'full';" in script_text
assert "detail: detailLevel" in script_text
assert "if (!isLiteSnapshot)" in script_text
assert "setInterval(() => load({lite:true}), 10000);" in script_text

print("ok: lite summary payload keeps totals but omits detail arrays for polling")
