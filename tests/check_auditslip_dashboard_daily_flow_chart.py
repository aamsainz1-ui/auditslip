#!/usr/bin/env python3
"""Guard: dashboard exposes a daily deposit/withdraw chart dataset and renderer."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TOKEN_DAILY_FLOW"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botflow:BOT_TOKEN:บริษัท Flow"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-daily-flow-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-daily-flow-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TOKEN_DAILY_FLOW", db_path=db_path, dry_run=True, bot_key="botflow", company_name="บริษัท Flow")
bot.init_db()

base = {
    "bot_key": "botflow",
    "company_name": "บริษัท Flow",
    "sender_name": "Uploader",
    "status": "success",
    "slip_time": "10:00",
    "transferor_name": "ลูกค้า",
    "recipient_name": "บริษัท Flow",
    "from_bank": "KBANK",
    "to_bank": "SCB",
    "from_account": "111",
    "to_account": "222",
    "confidence": 0.99,
}

bot.save_slip({**base, "id": "D1_WD", "chat_id": "CHAT_WD", "chat_title": "บริษัท Flow ถอน", "message_id": 11, "file_id": "FILE_D1_WD", "amount": 1000.0, "slip_date_display": "22/05/26", "slip_date_iso": "2026-05-22", "reference_no": "REF-D1-WD"})
bot.save_slip({**base, "id": "D1_DEP", "chat_id": "CHAT_DEP", "chat_title": "บริษัท Flow ฝาก", "message_id": 12, "file_id": "FILE_D1_DEP", "amount": 300.0, "slip_date_display": "22/05/26", "slip_date_iso": "2026-05-22", "reference_no": "REF-D1-DEP"})
bot.save_slip({**base, "id": "D2_WD", "chat_id": "CHAT_WD", "chat_title": "บริษัท Flow ถอน", "message_id": 21, "file_id": "FILE_D2_WD", "amount": 2000.0, "slip_date_display": "21/05/26", "slip_date_iso": "2026-05-21", "reference_no": "REF-D2-WD"})
# Duplicate deposit must not inflate the financial chart.
bot.save_slip({**base, "id": "D1_DEP_DUP", "chat_id": "CHAT_DEP", "chat_title": "บริษัท Flow ฝาก", "message_id": 13, "file_id": "FILE_D1_DEP_DUP", "amount": 300.0, "slip_date_display": "22/05/26", "slip_date_iso": "2026-05-22", "reference_no": "REF-D1-DEP", "is_duplicate": 1, "duplicate_of": "D1_DEP"})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snapshot = Dash.dashboard_snapshot(db_path, bot_key="botflow", flow_type="all", scope="all")
rows = {row["date_key"]: row for row in snapshot["daily_flow_summary"]}
assert rows["2026-05-22"]["withdraw_amount"] == 1000.0, rows
assert rows["2026-05-22"]["deposit_amount"] == 300.0, rows
assert rows["2026-05-22"]["total_amount"] == 1300.0, rows
assert rows["2026-05-22"]["deposit_count"] == 1, rows
assert rows["2026-05-21"]["withdraw_amount"] == 2000.0, rows
assert rows["2026-05-21"]["deposit_amount"] == 0.0, rows

html = Dash.render_dashboard_html("test-token")
for marker in [
    "dailyFlowChart",
    "renderDailyFlowChart",
    "data.daily_flow_summary",
    "กราฟรายวัน ฝาก/ถอน",
    "flow-chart",
    "flow-bar bar",
    "withdraw_amount",
    "deposit_amount",
]:
    assert marker in html, marker

print("ok: daily deposit/withdraw chart dataset and renderer")
