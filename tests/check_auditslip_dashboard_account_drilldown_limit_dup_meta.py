#!/usr/bin/env python3
"""Guard: account drill-down scrolls to slip cards, bot-scoped limits save, duplicate cards show group/bot context."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot6:BOT_TOKEN:บริษัท 6"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-account-drill-limit-dupe-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-account-drill-limit-dupe-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="bot6", company_name="บริษัท 6")
bot.init_db()

base = {
    "bot_key": "bot6",
    "company_name": "บริษัท 6",
    "sender_name": "Uploader",
    "username": "operator",
    "status": "success",
    "slip_date_display": "23/05/26",
    "slip_date_iso": "2026-05-23",
    "issuer_bank": "KBANK",
    "from_bank": "KBANK",
    "to_bank": "SCB",
    "confidence": 0.99,
}

# Withdrawal account row shown while the operator has selected only the company/bot, not a single chat.
bot.save_slip({
    **base,
    "id": "LIM-WD-1",
    "chat_id": "CHAT_WD",
    "chat_title": "บริษัท 6 ถอน",
    "message_id": 101,
    "file_id": "FILE_WD_1",
    "slip_time": "10:01",
    "transferor_name": "บัญชีถอนหนึ่ง",
    "recipient_name": "บริษัท 6",
    "from_account": "x-7061",
    "to_account": "ปลายทาง",
    "amount": 300.0,
})
bot.save_slip({
    **base,
    "id": "LIM-WD-2",
    "chat_id": "CHAT_WD",
    "chat_title": "บริษัท 6 ถอน",
    "message_id": 102,
    "file_id": "FILE_WD_2",
    "slip_time": "10:02",
    "transferor_name": "บัญชีถอนหนึ่ง",
    "recipient_name": "บริษัท 6",
    "from_account": "x-7061",
    "to_account": "ปลายทาง",
    "amount": 25.0,
})

# Duplicate pair in a deposit/manual-topup group; the card must show both company/bot and Telegram group context.
bot.save_slip({
    **base,
    "id": "ORIG-DUP-META",
    "chat_id": "CHAT_DEP",
    "chat_title": "666 สลิป (เติมมือ)",
    "message_id": 201,
    "file_id": "FILE_ORIG_DUP",
    "slip_time": "11:01",
    "transferor_name": "ลูกค้าฝาก",
    "recipient_name": "บริษัท 6",
    "from_account": "ต้นทางฝาก",
    "to_account": "x-7061",
    "amount": 500.0,
    "reference_no": "REF-DUP-META",
})
bot.save_slip({
    **base,
    "id": "DUP-META",
    "chat_id": "CHAT_DEP",
    "chat_title": "666 สลิป (เติมมือ)",
    "message_id": 202,
    "file_id": "FILE_DUP_META",
    "slip_time": "11:02",
    "transferor_name": "ลูกค้าฝาก",
    "recipient_name": "บริษัท 6",
    "from_account": "ต้นทางฝาก",
    "to_account": "x-7061",
    "amount": 500.0,
    "reference_no": "REF-DUP-META",
    "is_duplicate": 1,
    "duplicate_of": "ORIG-DUP-META",
})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

# Bot-level selection must be able to save and read back account limits.
snap = Dash.dashboard_snapshot(db_path, bot_key="bot6", flow_type="withdraw", scope="all")
row = next(r for r in snap["by_account_day"] if r["account"] == "x-7061")
assert row["daily_limit"] == 0.0, row
limit_key = row["limit_key"]
Dash.save_account_limit(db_path, "bot:bot6", limit_key, row["display_name"], row["bank"], row["account"], 999.0)
snap_after_limit = Dash.dashboard_snapshot(db_path, bot_key="bot6", flow_type="withdraw", scope="all")
row_after = next(r for r in snap_after_limit["by_account_day"] if r["account"] == "x-7061")
assert row_after["daily_limit"] == 999.0, row_after
assert row_after["remaining_amount"] == 674.0, row_after

# Duplicate pair API data must carry both duplicate and original context.
snap_dupe = Dash.dashboard_snapshot(db_path, bot_key="bot6", flow_type="deposit", scope="all", slip_filter="duplicate")
pair = next(r for r in snap_dupe["duplicate_pairs"] if r["duplicate_id"] == "DUP-META")
assert pair["duplicate_bot_key"] == "bot6", pair
assert pair["duplicate_company_name"] == "บริษัท 6", pair
assert pair["duplicate_chat_title"] == "666 สลิป (เติมมือ)", pair
assert pair["duplicate_flow_type"] == "deposit", pair
assert pair["original_bot_key"] == "bot6", pair
assert pair["original_company_name"] == "บริษัท 6", pair
assert pair["original_chat_title"] == "666 สลิป (เติมมือ)", pair
assert pair["original_flow_type"] == "deposit", pair

html = Dash.render_dashboard_html("test-token")
for marker in [
    "scrollElementIntoView(options.scrollTarget",
    "load({scrollTarget:'accountSlipSearch'",
    "function limitScopeKey()",
    "'bot:' + bot",
    "duplicateContextLine",
    "บริษัท/Bot",
    "กลุ่ม Telegram",
]:
    assert marker in html, marker

# The account drill-down button must not request top scrolling; the result cards live below the account index.
pick_fn = html[html.index("function pickAccountSearch"):html.index("function wireAccountSearchButtons")]
assert "scrollTop:true" not in pick_fn, pick_fn

print("ok: account drilldown scroll, bot-scoped limits, duplicate metadata")
