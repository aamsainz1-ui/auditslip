#!/usr/bin/env python3
"""Guard: choosing one company scopes operator panels to that company while keeping the company picker available."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN_1"] = "TOKEN1"
os.environ["BOT_TOKEN_2"] = "TOKEN2"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot1:BOT_TOKEN_1:บริษัท 1,bot2:BOT_TOKEN_2:บริษัท 2"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-company-scope-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-company-scope-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot1 = bot_mod.AuditslipBot(token="TOKEN1", db_path=db_path, dry_run=True, bot_key="bot1", company_name="บริษัท 1")
bot2 = bot_mod.AuditslipBot(token="TOKEN2", db_path=db_path, dry_run=True, bot_key="bot2", company_name="บริษัท 2")
bot1.init_db(); bot2.init_db()
base = {
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:00",
    "recipient_name": "ร้านค้า",
    "from_bank": "KBANK",
    "to_bank": "SCB",
    "amount": 100.0,
}
bot1.save_slip({**base, "id": "BOT1_ONLY", "bot_key": "bot1", "company_name": "บริษัท 1", "chat_id": "CHAT1", "chat_title": "บริษัท 1 ถอน", "message_id": 1, "file_id": "F1", "transferor_name": "ลูกค้า 1", "sender_name": "คนส่ง 1", "amount": 111.0, "reference_no": "REF1"})
bot2.save_slip({**base, "id": "BOT2_ONLY", "bot_key": "bot2", "company_name": "บริษัท 2", "chat_id": "CHAT2", "chat_title": "บริษัท 2 ถอน", "message_id": 2, "file_id": "F2", "transferor_name": "ลูกค้า 2", "sender_name": "คนส่ง 2", "amount": 222.0, "reference_no": "REF2"})

spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert spec and spec.loader
Dash = importlib.util.module_from_spec(spec)
sys.modules["auditslip_dashboard"] = Dash
spec.loader.exec_module(Dash)

snap_all = Dash.dashboard_snapshot(db_path, bot_key="__all__", flow_type="all", scope="open")
assert {r["bot_key"] for r in snap_all["company_summary"]} == {"bot1", "bot2"}, snap_all["company_summary"]

snap_bot1 = Dash.dashboard_snapshot(db_path, bot_key="bot1", flow_type="all", scope="open")
assert snap_bot1["selected_bot_key"] == "bot1", snap_bot1
assert {r["bot_key"] for r in snap_bot1["company_summary"]} == {"bot1"}, snap_bot1["company_summary"]
assert {r["bot_key"] for r in snap_bot1["company_menu"]} == {"bot1", "bot2"}, snap_bot1.get("company_menu")
assert snap_bot1["totals"]["selected_success_count"] == 1, snap_bot1["totals"]
assert snap_bot1["totals"]["selected_success_amount"] == 111.0, snap_bot1["totals"]
assert [row["id"] for row in snap_bot1["recent"]] == ["BOT1_ONLY"], snap_bot1["recent"]
assert [row["name"] for row in snap_bot1["by_sender"]] == ["คนส่ง 1"], snap_bot1["by_sender"]
assert [row["amount"] for row in snap_bot1["by_date"]] == [111.0], snap_bot1["by_date"]

html = Dash.render_dashboard_html("test-token")
for marker in [
    "company_menu",
    "renderSideCompanies(data.company_menu || data.company_summary)",
    "renderCompanyOverview(data.company_summary)",
    "บริษัทที่เลือก",
]:
    assert marker in html, marker

print("ok: selected company dashboard panels do not mix other companies")
