#!/usr/bin/env python3
"""Guard: company/bot dropdown lists all configured companies even before a bot has group data."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TOKEN6"
os.environ["BOT_TOKEN_1"] = "TOKEN1"
os.environ["BOT_TOKEN_2"] = "TOKEN2"
os.environ["BOT_TOKEN_3"] = "TOKEN3"
os.environ["BOT_TOKEN_4"] = "TOKEN4"
os.environ["BOT_TOKEN_5"] = "TOKEN5"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot1:BOT_TOKEN_1:บริษัท 1,bot2:BOT_TOKEN_2:บริษัท 2,bot3:BOT_TOKEN_3:บริษัท 3,bot4:BOT_TOKEN_4:บริษัท 4,bot5:BOT_TOKEN_5:บริษัท 5,bot6:BOT_TOKEN:บริษัท 6 Audit"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-company-dropdown-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-company-dropdown-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

bot = bot_mod.AuditslipBot(token="TOKEN6", db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True, bot_key="bot6", company_name="บริษัท 6 Audit")
bot.init_db()
bot.save_slip({
    "id": "ONLY_BOT6",
    "bot_key": "bot6",
    "company_name": "บริษัท 6 Audit",
    "chat_id": "CHAT6",
    "chat_title": "กลุ่มบริษัท 6",
    "message_id": 1,
    "file_id": "FILE6",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:00",
    "transferor_name": "คุณเอ",
    "amount": 100.0,
    "confidence": 0.99,
})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snap = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]), bot_key="bot1", scope="open")
assert len(snap["telegram_bots"]) == 6, snap["telegram_bots"]
assert [b["company_name"] for b in snap["telegram_bots"]] == ["บริษัท 1", "บริษัท 2", "บริษัท 3", "บริษัท 4", "บริษัท 5", "บริษัท 6"], snap["telegram_bots"]
assert all("audit" not in b["company_name"].lower() for b in snap["telegram_bots"]), snap["telegram_bots"]
assert snap["selected_bot_key"] == "bot1", snap
assert snap["selected_chat_id"] == "", snap
assert snap["chats"] and snap["chats"][0]["bot_key"] == "bot6", snap["chats"]

html = Dash.render_dashboard_html("test-token")
for marker in ["botFilter", "selectedBotKey", "ยังไม่มีกลุ่มของบริษัทนี้", "เลือกบริษัท/บอท"]:
    assert marker in html, marker

print("ok: dashboard company dropdown lists all configured bots")
