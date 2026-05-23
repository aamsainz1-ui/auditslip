#!/usr/bin/env python3
"""Guard: dashboard can use OpenAI provider to double-check missing source/destination banks."""
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
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-openai-bank-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-openai-bank-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"
os.environ["OPENAI_MODEL"] = "gpt-test-bank-review"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="bot1", company_name="บริษัท 1")
bot.init_db()
bot.save_slip({
    "id": "MISS_BANKS",
    "bot_key": "bot1",
    "company_name": "บริษัท 1",
    "chat_id": "CHAT1",
    "chat_title": "บริษัท 1 ถอน",
    "sender_name": "Uploader",
    "message_id": 100,
    "file_id": "FILE_BANKS",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:00",
    "transferor_name": "คุณเอ",
    "recipient_name": "บริษัท 1",
    "issuer_bank": "",
    "from_bank": "",
    "to_bank": "ไม่ทราบ",
    "amount": 100.0,
    "reference_no": "REF100",
})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

calls = []
def fake_fetch_slip_image(db_path_arg, slip_id):
    calls.append(("fetch", str(slip_id)))
    return b"fake-image", "image/jpeg"

def fake_openai_extract(image_path, mime=None):
    calls.append(("openai", Path(image_path).exists(), mime))
    return {
        "issuer_bank": "กสิกรไทย",
        "from_bank": "ไทยพาณิชย์",
        "to_bank": "กรุงไทย",
        "confidence": 0.91,
        "raw_text": "OpenAI recheck saw SCB -> KTB",
    }, {"provider": "openai", "model": "gpt-test-bank-review"}

Dash.fetch_slip_image = fake_fetch_slip_image
Dash.openai_extract = fake_openai_extract

before = Dash.dashboard_snapshot(db_path, chat_id="CHAT1", bot_key="bot1", flow_type="withdraw", scope="open")
assert before["totals"]["source_bank_review_count"] == 1, before["source_bank_review"]

result = Dash.openai_bank_double_check_slip(db_path, "MISS_BANKS", apply=True)
assert result["ok"] is True, result
assert result["provider"] == "openai", result
assert result["model"] == "gpt-test-bank-review", result
assert result["suggested"]["from_bank"] == "SCB", result
assert result["suggested"]["to_bank"] == "KRUNGTHAI", result
assert result["applied"]["from_bank"] == "SCB", result
assert result["applied"]["to_bank"] == "KRUNGTHAI", result
assert calls and calls[0] == ("fetch", "MISS_BANKS") and calls[1][0] == "openai", calls

with sqlite3.connect(db_path) as conn:
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT issuer_bank, from_bank, to_bank FROM slips WHERE id='MISS_BANKS'").fetchone()
    log_count = conn.execute("SELECT COUNT(*) AS count FROM bank_review_logs WHERE slip_id='MISS_BANKS'").fetchone()["count"]
assert dict(row) == {"issuer_bank": "KBANK", "from_bank": "SCB", "to_bank": "KRUNGTHAI"}, dict(row)
assert log_count == 1, log_count

after = Dash.dashboard_snapshot(db_path, chat_id="CHAT1", bot_key="bot1", flow_type="withdraw", scope="open")
assert after["totals"]["source_bank_review_count"] == 0, after["source_bank_review"]

bot.save_slip({
    "id": "MASKED_SOURCE",
    "bot_key": "bot1",
    "company_name": "บริษัท 1",
    "chat_id": "CHAT1",
    "chat_title": "บริษัท 1 ถอน",
    "sender_name": "Uploader",
    "message_id": 101,
    "file_id": "FILE_MASKED_SOURCE",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:05",
    "transferor_name": "คุณบี",
    "recipient_name": "บริษัท 1",
    "issuer_bank": "ไทยพาณิชย์",
    "from_bank": "",
    "to_bank": "กรุงไทย",
    "amount": 200.0,
    "reference_no": "REF101",
})

masked_before = Dash.dashboard_snapshot(db_path, chat_id="CHAT1", bot_key="bot1", flow_type="withdraw", scope="open")
assert masked_before["totals"]["source_bank_review_count"] == 0, masked_before["source_bank_review"]

def fake_openai_extract_masked_source(image_path, mime=None):
    return {
        "issuer_bank": "ไทยพาณิชย์",
        "from_bank": "XXX",
        "to_bank": "กรุงไทย",
        "confidence": 0.88,
        "raw_text": "SCB slip masks the source account as xxx",
    }, {"provider": "openai", "model": "gpt-test-bank-review"}

Dash.openai_extract = fake_openai_extract_masked_source
masked_result = Dash.openai_bank_double_check_slip(db_path, "MASKED_SOURCE", apply=True)
assert masked_result["ok"] is True, masked_result
assert masked_result["suggested"]["from_bank"] == "SCB", masked_result
assert masked_result["applied"]["from_bank"] == "SCB", masked_result
with sqlite3.connect(db_path) as conn:
    conn.row_factory = sqlite3.Row
    masked_row = conn.execute("SELECT issuer_bank, from_bank, to_bank FROM slips WHERE id='MASKED_SOURCE'").fetchone()
assert dict(masked_row) == {"issuer_bank": "SCB", "from_bank": "SCB", "to_bank": "KRUNGTHAI"}, dict(masked_row)
masked_after = Dash.dashboard_snapshot(db_path, chat_id="CHAT1", bot_key="bot1", flow_type="withdraw", scope="open")
assert masked_after["totals"]["source_bank_review_count"] == 0, masked_after["source_bank_review"]

html = Dash.render_dashboard_html("test-token")
for marker in ["openaiBankRecheck", "/api/bank-review/openai", "OpenAI รีเช็คธนาคาร", "รีเช็คธนาคารต้นทาง"]:
    assert marker in html, marker

print("ok: OpenAI double-check fills missing source/destination banks and logs review")
