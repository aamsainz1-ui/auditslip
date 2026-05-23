#!/usr/bin/env python3
"""Guard: dashboard Excel export follows the selected company/bot, not a stale chat dropdown."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TOKEN6"
os.environ["BOT_TOKEN_3"] = "TOKEN3"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot3:BOT_TOKEN_3:บริษัท 3,bot6:BOT_TOKEN:บริษัท 6"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-export-company-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-export-company-out-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot3 = bot_mod.AuditslipBot(token="TOKEN3", db_path=db_path, dry_run=True, bot_key="bot3", company_name="บริษัท 3")
bot6 = bot_mod.AuditslipBot(token="TOKEN6", db_path=db_path, dry_run=True, bot_key="bot6", company_name="บริษัท 6")
bot3.init_db()
bot6.init_db()
base = {
    "chat_title": "Audit Room",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:00",
    "transferor_name": "คุณเอ",
    "recipient_name": "ร้านค้า",
    "from_bank": "KBANK",
    "to_bank": "SCB",
    "amount": 100.0,
    "reference_no": "REF-BASE",
}
bot6.save_slip({**base, "id": "B6", "bot_key": "bot6", "company_name": "บริษัท 6", "chat_id": "CHAT6", "message_id": 6, "file_id": "FILE6", "amount": 600.0, "reference_no": "REF6"})
bot3.save_slip({**base, "id": "B3", "bot_key": "bot3", "company_name": "บริษัท 3", "chat_id": "CHAT3", "message_id": 3, "file_id": "FILE3", "amount": 300.0, "reference_no": "REF3"})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

# Regression: if the UI has selected bot3 but the chat dropdown/link still carries old bot6 chat,
# the server must ignore the stale chat and export bot3's chat instead.
sel = Dash.resolve_export_selection(db_path, chat_id="CHAT6", bot_key="bot3")
assert sel["ok"] is True, sel
assert sel["bot_key"] == "bot3", sel
assert sel["chat_id"] == "CHAT3", sel
assert sel["stale_chat_replaced"] is True, sel

# No chat_id with bot3 should also resolve inside bot3, never fall back to first/highest bot6.
sel = Dash.resolve_export_selection(db_path, chat_id="", bot_key="bot3")
assert sel["ok"] is True and sel["bot_key"] == "bot3" and sel["chat_id"] == "CHAT3", sel

html = Dash.render_dashboard_html("test-token")
for marker in ["exportExcel()", "buildExcelUrl", "return true;"]:
    assert marker in html, marker

# The export link already carries bot_key from exportCompanyFilter and the backend resolves stale chats.
# Do not block the first tap while /api/summary is still refreshing, or mobile users see "no file/data".
assert "Excel กำลังเปลี่ยนบริษัท" not in html
assert "load({scrollTop:true});\n    return false;" not in html

print("ok: dashboard Excel export follows selected company")
