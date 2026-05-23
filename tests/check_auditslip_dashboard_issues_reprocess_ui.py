#!/usr/bin/env python3
"""Guard: dashboard Issues show evidence and can re-run OCR for one bad slip."""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot1:BOT_TOKEN:บริษัท 1"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-issues-reprocess-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-issues-reprocess-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="bot1", company_name="บริษัท 1")
bot.init_db()
bot.save_slip({
    "id": "ISSUE1",
    "bot_key": "bot1",
    "company_name": "บริษัท 1",
    "chat_id": "CHAT1",
    "chat_title": "บริษัท 1 ถอน",
    "message_id": 501,
    "file_id": "FILE_ISSUE1",
    "sender_name": "Uploader",
    "status": "unclear",
    "error": "missing amount",
    "confidence": 0.30,
    "raw_text": "เห็นชื่อแต่ไม่เห็นยอด",
})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash: Any = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snap = Dash.dashboard_snapshot(db_path, chat_id="CHAT1", bot_key="bot1", scope="open")
assert len(snap["issues"]) == 1, snap["issues"]
assert snap["issues"][0]["image_url"].endswith("id=ISSUE1"), snap["issues"][0]

calls = []
def fake_fetch(db_path_arg, slip_id):
    calls.append(("fetch", slip_id))
    return b"fake-image", "image/jpeg"

def fake_ocr(path, mime):
    calls.append(("ocr", Path(path).exists(), mime))
    return "openai", {
        "slip_date_display": "22/05/26",
        "slip_date_iso": "2026-05-22",
        "slip_time": "12:34",
        "transferor_name": "คุณทดสอบ",
        "recipient_name": "บริษัท 1",
        "from_bank": "SCB",
        "from_account": "111-xxx-222",
        "to_bank": "KBANK",
        "to_account": "999-xxx-888",
        "amount": 123.45,
        "reference_no": "REFISSUE1",
        "confidence": 0.94,
    }

Dash.fetch_slip_image = fake_fetch
Dash.ocr_extract = fake_ocr
result = Dash.reprocess_dashboard_slip(db_path, "ISSUE1", bot_key="bot1")
assert result["ok"] is True, result
assert result["status"] == "success", result
assert result["amount"] == 123.45, result
assert calls[0] == ("fetch", "ISSUE1") and calls[1][0] == "ocr", calls

with sqlite3.connect(db_path) as conn:
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT status, error, amount, from_bank, to_bank FROM slips WHERE id='ISSUE1'").fetchone()
assert dict(row) == {"status": "success", "error": "", "amount": 123.45, "from_bank": "SCB", "to_bank": "KBANK"}, dict(row)

html = Dash.render_dashboard_html("test-token")
for marker in ["renderQueueIssues", "reprocessIssue", "/api/slip/reprocess", "รี OCR", "รี OCR Issues ในขอบเขตนี้", "ไม่มีรายการ error/อ่านไม่ชัด"]:
    assert marker in html, marker

print("ok: dashboard issues show evidence and can re-run OCR")
