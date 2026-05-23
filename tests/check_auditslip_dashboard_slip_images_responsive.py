#!/usr/bin/env python3
"""Guard: dashboard recent slip cards show Telegram slip images and responsive/mobile markers."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-image-dash-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-image-dash-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True, bot_key="bot1", company_name="บริษัท 1")
bot.init_db()
bot.save_slip({
    "id": "IMG1",
    "bot_key": "bot1",
    "company_name": "บริษัท 1",
    "chat_id": "CHAT1",
    "chat_title": "Audit Room",
    "message_id": 1,
    "file_id": "FILE_IMAGE_1",
    "sender_name": "Alice",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:00",
    "transferor_name": "คุณเอ",
    "from_bank": "SCB",
    "to_bank": "KBank",
    "amount": 100.0,
    "confidence": 0.99,
})
bot.save_slip({
    "id": "IMG_DUP",
    "bot_key": "bot1",
    "company_name": "บริษัท 1",
    "chat_id": "CHAT1",
    "chat_title": "Audit Room",
    "message_id": 2,
    "file_id": "FILE_IMAGE_DUP",
    "sender_name": "Bob",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:05",
    "transferor_name": "คุณเอ",
    "from_bank": "SCB",
    "to_bank": "KBank",
    "amount": 100.0,
    "confidence": 0.99,
    "is_duplicate": 1,
    "duplicate_of": "IMG1",
})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snapshot = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]), chat_id="CHAT1", scope="open")
recent = {row["id"]: row for row in snapshot["recent"]}
assert recent["IMG1"]["file_id"] == "FILE_IMAGE_1", recent
assert recent["IMG1"]["bot_key"] == "bot1", recent
assert recent["IMG1"]["company_name"] == "บริษัท 1", recent
assert recent["IMG1"]["image_url"].startswith("/api/slip-image?id=IMG1"), recent
assert recent["IMG_DUP"]["is_duplicate"] == 1 and recent["IMG_DUP"]["image_url"].startswith("/api/slip-image?id=IMG_DUP"), recent
assert snapshot["chats"][0]["company_name"] == "บริษัท 1", snapshot["chats"]

dup_snapshot = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]), chat_id="CHAT1", scope="open", slip_filter="duplicate")
assert [row["id"] for row in dup_snapshot["recent"]] == ["IMG_DUP"], dup_snapshot["recent"]
assert dup_snapshot["recent"][0]["duplicate_of"] == "IMG1", dup_snapshot["recent"]

html = Dash.render_dashboard_html("test-token")
for marker in [
    "slip-thumb",
    "image_url",
    "responsive-table",
    "@media (max-width: 720px)",
    "min-width:0",
    "overflow:hidden",
    "<link rel=\"icon\" href=\"data:,\" />",
    "botSettings",
    "telegramBots",
    "botFilter",
    "เลือกบริษัท/บอท",
    "ตั้งค่าบอท Telegram",
    "slipFilter",
    "duplicateOnly",
    "สลิปซ้ำที่จับแล้ว",
]:
    assert marker in html, marker

print("ok: dashboard slip images + responsive markers")
