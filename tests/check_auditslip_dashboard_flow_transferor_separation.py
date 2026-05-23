#!/usr/bin/env python3
"""Guard: all-flow dashboard keeps deposit customer slips out of withdrawal/limit transferor panels."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TOKEN3"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot3:BOT_TOKEN:บริษัท 3"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-flow-transferor-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-flow-transferor-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TOKEN3", db_path=db_path, dry_run=True, bot_key="bot3", company_name="บริษัท 3")
bot.init_db()
base = {
    "bot_key": "bot3",
    "company_name": "บริษัท 3",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:00",
    "transferor_name": "ลูกค้าเอ",
    "recipient_name": "บริษัท 3",
    "from_bank": "SCB",
    "from_account": "111-xxx-222",
    "to_bank": "KBANK",
    "amount": 100.0,
    "reference_no": "REF-BASE",
}
bot.save_slip({**base, "id": "WD1", "chat_id": "CHAT_WITHDRAW", "chat_title": "บริษัท 3 ถอน", "message_id": 11, "file_id": "FILE_WD", "amount": 1000.0, "reference_no": "REF-WD"})
bot.save_slip({**base, "id": "DEP1", "chat_id": "CHAT_DEPOSIT", "chat_title": "บริษัท 3 เติมมือ", "message_id": 21, "file_id": "FILE_DEP", "amount": 300.0, "reference_no": "REF-DEP"})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snap_all = Dash.dashboard_snapshot(db_path, bot_key="bot3", flow_type="all", scope="open")
assert snap_all["totals"]["selected_success_count"] == 2, snap_all["totals"]
assert snap_all["totals"]["selected_success_amount"] == 1300.0, snap_all["totals"]
assert snap_all["limit_check_enabled"] is True, snap_all

by_transferor = {row["name"]: row for row in snap_all["by_transferor"]}
assert list(by_transferor) == ["ลูกค้าเอ (SCB)"], by_transferor
assert by_transferor["ลูกค้าเอ (SCB)"]["count"] == 1, by_transferor
assert by_transferor["ลูกค้าเอ (SCB)"]["amount"] == 1000.0, by_transferor
by_day = {(row["date"], row["name"]): row for row in snap_all["by_account_day"]}
assert list(by_day.values())[0]["count"] == 1, by_day
assert list(by_day.values())[0]["amount"] == 1000.0, by_day

customer_slips = snap_all["deposit_customer_slips"]
assert [row["id"] for row in customer_slips] == ["DEP1"], customer_slips
assert customer_slips[0]["amount"] == 300.0 and customer_slips[0]["flow_type"] == "deposit", customer_slips
assert snap_all["totals"]["deposit_customer_count"] == 1, snap_all["totals"]
assert snap_all["totals"]["deposit_customer_amount"] == 300.0, snap_all["totals"]

snap_dep = Dash.dashboard_snapshot(db_path, bot_key="bot3", flow_type="deposit", scope="open")
assert snap_dep["limit_check_enabled"] is False, snap_dep
assert snap_dep["by_transferor"] == [] and snap_dep["by_account_day"] == [], snap_dep
assert [row["id"] for row in snap_dep["deposit_customer_slips"]] == ["DEP1"], snap_dep["deposit_customer_slips"]

html = Dash.render_dashboard_html("test-token")
for marker in ["depositCustomerSlips", "สลิปลูกค้าฝาก/เติมมือ", "ไม่เอาไปรวมกับถอน/วงเงิน"]:
    assert marker in html, marker

print("ok: all-flow transferor/limits exclude deposit customer slips and show them separately")
