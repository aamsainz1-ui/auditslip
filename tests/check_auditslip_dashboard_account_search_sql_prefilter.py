#!/usr/bin/env python3
"""Guard: account slip audit search applies a SQL-side prefilter before Python matching.

Without the prefilter, searching one account scans every counted slip in the selected
scope and makes mobile drills slow on production-sized days. The function should only
run the Python side matcher on rows that could contain the account/name query.
"""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot1:BOT_TOKEN:บริษัท 1"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-search-prefilter-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-search-prefilter-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="bot1", company_name="บริษัท 1")
bot.init_db()

for i in range(120):
    bot.save_slip({
        "id": f"NOISE-{i}",
        "bot_key": "bot1",
        "company_name": "บริษัท 1",
        "chat_id": "CHAT_WD",
        "chat_title": "บริษัท 1 ถอน",
        "message_id": i + 1,
        "file_id": f"FILE_NOISE_{i}",
        "sender_name": "Uploader",
        "status": "success",
        "slip_date_display": "23/05/26",
        "slip_date_iso": "2026-05-23",
        "slip_time": "10:00",
        "transferor_name": f"ลูกค้า noise {i}",
        "recipient_name": "บริษัท 1",
        "from_bank": "SCB",
        "from_account": f"900-000-{i:03d}",
        "to_bank": "KBANK",
        "to_account": f"800-000-{i:03d}",
        "amount": 1000.0 + i,
        "reference_no": f"NOISE{i:03d}",
    })

bot.save_slip({
    "id": "MATCH-1",
    "bot_key": "bot1",
    "company_name": "บริษัท 1",
    "chat_id": "CHAT_WD",
    "chat_title": "บริษัท 1 ถอน",
    "message_id": 999,
    "file_id": "FILE_MATCH",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "23/05/26",
    "slip_date_iso": "2026-05-23",
    "slip_time": "11:00",
    "transferor_name": "ลูกค้าตรงบัญชี",
    "recipient_name": "บริษัท 1",
    "from_bank": "SCB",
    "from_account": "123-456-7890",
    "to_bank": "KBANK",
    "to_account": "111-222-333",
    "amount": 9999.0,
    "reference_no": "MATCH001",
})

spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert spec and spec.loader
Dash = importlib.util.module_from_spec(spec)
sys.modules["auditslip_dashboard"] = Dash
spec.loader.exec_module(Dash)

calls = {"count": 0}
orig_match = getattr(Dash, "account_slip_match")

def counted_match(row, query):
    calls["count"] += 1
    return orig_match(row, query)

setattr(Dash, "account_slip_match", counted_match)
where_clause = "COALESCE(status,'success')='success' AND COALESCE(is_duplicate,0)=0"
with sqlite3.connect(db_path) as conn:
    conn.row_factory = sqlite3.Row
    result = Dash.account_slip_search_rows(conn, where_clause, [], "1234567890")

assert result["count"] == 1, result
assert result["rows"][0]["id"] == "MATCH-1", result["rows"]
assert calls["count"] <= 5, f"Python matcher scanned {calls['count']} rows; SQL prefilter is missing"
print("ok: account slip search uses SQL-side prefilter before Python matching")
