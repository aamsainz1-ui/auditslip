#!/usr/bin/env python3
"""Guard: one company bot can serve separate deposit/withdraw groups without mixing totals."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TOKEN3"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot3:BOT_TOKEN:บริษัท 3"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-flow-filter-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-flow-filter-export-")))
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
    "transferor_name": "ลูกค้า",
    "recipient_name": "บริษัท 3",
    "from_bank": "KBANK",
    "to_bank": "SCB",
    "amount": 100.0,
    "reference_no": "REF-BASE",
}
bot.save_slip({**base, "id": "WD1", "chat_id": "CHAT_WITHDRAW", "chat_title": "บริษัท 3 ถอน", "message_id": 11, "file_id": "FILE_WD", "amount": 1000.0, "reference_no": "REF-WD"})
bot.save_slip({**base, "id": "DEP1", "chat_id": "CHAT_DEPOSIT", "chat_title": "บริษัท 3 ฝาก", "message_id": 21, "file_id": "FILE_DEP", "amount": 300.0, "reference_no": "REF-DEP"})
bot.save_slip({**base, "id": "DEP_DUP", "chat_id": "CHAT_DEPOSIT", "chat_title": "บริษัท 3 ฝาก", "message_id": 22, "file_id": "FILE_DEP_DUP", "amount": 300.0, "reference_no": "REF-DEP", "is_duplicate": 1, "duplicate_of": "DEP1"})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snap_all = Dash.dashboard_snapshot(db_path, bot_key="bot3", flow_type="all", scope="open")
assert snap_all["selected_bot_key"] == "bot3", snap_all
assert snap_all["selected_chat_id"] == "", snap_all
company = next(r for r in snap_all["company_summary"] if r["bot_key"] == "bot3")
assert company["deposit_open_count"] == 1, company
assert company["deposit_open_amount"] == 300.0, company
assert company["withdraw_open_count"] == 1, company
assert company["withdraw_open_amount"] == 1000.0, company

snap_dep = Dash.dashboard_snapshot(db_path, bot_key="bot3", flow_type="deposit", scope="open")
assert snap_dep["selected_bot_key"] == "bot3", snap_dep
assert snap_dep["selected_chat_id"] == "", snap_dep
assert snap_dep["flow_type"] == "deposit", snap_dep
assert snap_dep["totals"]["selected_success_count"] == 1, snap_dep["totals"]
assert snap_dep["totals"]["selected_success_amount"] == 300.0, snap_dep["totals"]
assert {r["chat_id"] for r in snap_dep["recent"]} == {"CHAT_DEPOSIT"}, snap_dep["recent"]
assert snap_dep["totals"]["selected_duplicate_count"] == 1, snap_dep["totals"]

snap_wd = Dash.dashboard_snapshot(db_path, bot_key="bot3", flow_type="withdraw", scope="open")
assert snap_wd["selected_chat_id"] == "", snap_wd
assert snap_wd["totals"]["selected_success_count"] == 1, snap_wd["totals"]
assert snap_wd["totals"]["selected_success_amount"] == 1000.0, snap_wd["totals"]
assert {r["chat_id"] for r in snap_wd["recent"]} == {"CHAT_WITHDRAW"}, snap_wd["recent"]

chats = {r["chat_id"]: r["flow_type"] for r in snap_wd["chats"]}
assert chats["CHAT_DEPOSIT"] == "deposit", chats
assert chats["CHAT_WITHDRAW"] == "withdraw", chats

sel = Dash.resolve_export_selection(db_path, chat_id="", bot_key="bot3", flow_type="deposit")
assert sel["ok"] is True and sel["chat_id"] == "CHAT_DEPOSIT" and sel["flow_type"] == "deposit", sel

html = Dash.render_dashboard_html("test-token")
for marker in ["flowFilter", "ฝาก", "ถอน", "flow_type", "ทุกกลุ่มฝาก", "ทุกกลุ่มถอน", "ยอดฝาก", "ยอดถอน", "สลิปฝาก", "สลิปถอน"]:
    assert marker in html, marker

print("ok: dashboard separates deposit/withdraw groups for same bot")
