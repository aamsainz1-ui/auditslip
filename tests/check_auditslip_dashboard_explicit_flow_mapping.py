#!/usr/bin/env python3
"""Guard: explicit bot/chat flow mapping overrides title heuristics for dashboard totals."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A"
os.environ["AUDITSLIP_FLOW_MAP"] = json.dumps({
    "botA|CHAT_GENERIC_DEP": "deposit",
    "botA|CHAT_GENERIC_WD": "withdraw",
}, ensure_ascii=False)
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-flow-map-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-flow-map-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="botA", company_name="บริษัท A")
bot.init_db()

base = {
    "bot_key": "botA",
    "company_name": "บริษัท A",
    "chat_title": "ห้องรวมไม่มีคำฝากถอน",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:00",
    "transferor_name": "ลูกค้า",
    "recipient_name": "บริษัท A",
    "from_bank": "SCB",
    "from_account": "FROM-ACC",
    "to_bank": "KBANK",
    "to_account": "TO-ACC",
    "confidence": 0.99,
}

bot.save_slip({**base, "id": "MAPPED_DEP", "chat_id": "CHAT_GENERIC_DEP", "message_id": 1, "file_id": "FILE_DEP", "amount": 100.0, "from_account": "DEP-FROM", "to_account": "DEP-TO", "reference_no": "DEP"})
bot.save_slip({**base, "id": "MAPPED_WD", "chat_id": "CHAT_GENERIC_WD", "message_id": 2, "file_id": "FILE_WD", "amount": 900.0, "from_account": "WD-FROM", "to_account": "WD-TO", "reference_no": "WD"})
bot.save_slip({**base, "id": "LEGACY_WD", "chat_id": "CHAT_LEGACY", "message_id": 3, "file_id": "FILE_LEGACY", "amount": 50.0, "from_account": "LEGACY-FROM", "to_account": "LEGACY-TO", "reference_no": "LEGACY"})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

assert Dash.flow_type_for_title("ห้องรวมไม่มีคำฝากถอน", bot_key="botA", chat_id="CHAT_GENERIC_DEP") == "deposit"
assert Dash.flow_type_for_title("ห้องรวมไม่มีคำฝากถอน", bot_key="botA", chat_id="CHAT_GENERIC_WD") == "withdraw"
assert Dash.flow_type_for_title("ห้องรวมไม่มีคำฝากถอน", bot_key="botA", chat_id="CHAT_LEGACY") == "withdraw"

snap_dep = Dash.dashboard_snapshot(db_path, bot_key="botA", flow_type="deposit", scope="2026-05-22")
assert snap_dep["totals"]["selected_success_count"] == 1, snap_dep["totals"]
assert snap_dep["totals"]["selected_success_amount"] == 100.0, snap_dep["totals"]
assert {r["id"] for r in snap_dep["recent"]} == {"MAPPED_DEP"}, snap_dep["recent"]
assert {(r["account"], r["flow_type"], r["account_role"]) for r in snap_dep["company_account_daily"]} == {("DEP-TO", "deposit", "บัญชีรับเงิน/ปลายทาง")}, snap_dep["company_account_daily"]

snap_wd = Dash.dashboard_snapshot(db_path, bot_key="botA", flow_type="withdraw", scope="2026-05-22")
assert snap_wd["totals"]["selected_success_count"] == 2, snap_wd["totals"]
assert snap_wd["totals"]["selected_success_amount"] == 950.0, snap_wd["totals"]
assert {r["id"] for r in snap_wd["recent"]} == {"MAPPED_WD", "LEGACY_WD"}, snap_wd["recent"]
assert {(r["account"], r["flow_type"], r["account_role"]) for r in snap_wd["company_account_daily"]} == {("WD-FROM", "withdraw", "บัญชีผู้โอน/ต้นทาง"), ("LEGACY-FROM", "withdraw", "บัญชีผู้โอน/ต้นทาง")}, snap_wd["company_account_daily"]

chat_flows = {row["chat_id"]: row["flow_type"] for row in snap_wd["chats"]}
assert chat_flows["CHAT_GENERIC_DEP"] == "deposit", chat_flows
assert chat_flows["CHAT_GENERIC_WD"] == "withdraw", chat_flows
assert chat_flows["CHAT_LEGACY"] == "withdraw", chat_flows

print("ok: explicit flow mapping overrides generic chat-title heuristics")
