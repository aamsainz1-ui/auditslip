#!/usr/bin/env python3
"""Guard: dashboard shows duplicate pairs and slips needing source-bank review."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-dupe-bank-review-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-dupe-bank-review-export-")))
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

base = {
    "bot_key": "bot1",
    "company_name": "บริษัท 1",
    "chat_id": "CHAT1",
    "chat_title": "Audit Room",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:00",
    "transferor_name": "คุณเอ",
    "recipient_name": "ร้านค้า",
    "from_bank": "SCB",
    "from_account": "111-xxx-222",
    "to_bank": "KBANK",
    "to_account": "333-xxx-444",
    "amount": 100.0,
    "reference_no": "REF100",
    "confidence": 0.99,
}

bot.save_slip({**base, "id": "ORIG", "message_id": 1, "file_id": "FILE_ORIG"})
bot.save_slip({**base, "id": "DUP", "message_id": 2, "file_id": "FILE_DUP", "is_duplicate": 1, "duplicate_of": "ORIG"})
bot.save_slip({
    **base,
    "id": "MISS_BANK",
    "message_id": 3,
    "file_id": "FILE_MISS_BANK",
    "slip_time": "10:30",
    "transferor_name": "คุณบี",
    "from_bank": "",
    "from_account": "999-xxx-000",
    "issuer_bank": "กรุงไทย",
    "to_bank": "ไทยพาณิชย์",
    "amount": 250.0,
    "reference_no": "REF250",
})
bot.save_slip({
    **base,
    "id": "MISS_DEST_BANK",
    "message_id": 4,
    "file_id": "FILE_MISS_DEST_BANK",
    "slip_time": "10:45",
    "transferor_name": "คุณซี",
    "from_bank": "ไทยพาณิชย์",
    "to_bank": "",
    "amount": 350.0,
    "reference_no": "REF350",
})
bot.save_slip({
    **base,
    "id": "MISS_TRUE_SOURCE_BANK",
    "message_id": 6,
    "file_id": "FILE_MISS_TRUE_SOURCE_BANK",
    "slip_time": "10:55",
    "transferor_name": "คุณดี",
    "from_bank": "",
    "issuer_bank": "",
    "to_bank": "ไทยพาณิชย์",
    "amount": 450.0,
    "reference_no": "REF450",
})

# Missing-bank duplicate should not pollute counted bank review.
bot.save_slip({
    **base,
    "id": "MISS_BANK_DUP",
    "message_id": 5,
    "file_id": "FILE_MISS_BANK_DUP",
    "slip_time": "10:30",
    "from_bank": "",
    "amount": 250.0,
    "is_duplicate": 1,
    "duplicate_of": "MISS_BANK",
})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snapshot = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]), chat_id="CHAT1", bot_key="bot1", scope="open")

pairs = snapshot["duplicate_pairs"]
assert len(pairs) == 2, pairs
by_dup = {row["duplicate_id"]: row for row in pairs}
assert by_dup["DUP"]["original_id"] == "ORIG", by_dup
assert by_dup["DUP"]["duplicate_image_url"].startswith("/api/slip-image?id=DUP"), by_dup["DUP"]
assert by_dup["DUP"]["original_image_url"].startswith("/api/slip-image?id=ORIG"), by_dup["DUP"]
assert by_dup["DUP"]["duplicate_message_id"] == 2 and by_dup["DUP"]["original_message_id"] == 1, by_dup["DUP"]
assert by_dup["DUP"]["amount"] == 100.0 and by_dup["DUP"]["transferor_name"] == "คุณเอ", by_dup["DUP"]
assert by_dup["MISS_BANK_DUP"]["original_id"] == "MISS_BANK", by_dup

review = snapshot["source_bank_review"]
by_review_id = {row["id"]: row for row in review}
assert set(by_review_id) == {"MISS_TRUE_SOURCE_BANK"}, review
assert by_review_id["MISS_TRUE_SOURCE_BANK"]["issuer_bank"] == "", review
assert by_review_id["MISS_TRUE_SOURCE_BANK"]["to_bank"] == "SCB", review
assert by_review_id["MISS_TRUE_SOURCE_BANK"]["image_url"].startswith("/api/slip-image?id=MISS_TRUE_SOURCE_BANK"), by_review_id["MISS_TRUE_SOURCE_BANK"]
assert snapshot["totals"]["source_bank_review_count"] == 1, snapshot["totals"]

html = Dash.render_dashboard_html("test-token")
for marker in ["duplicatePairs", "คู่สลิปซ้ำ", "ซ้ำกับใบ", "renderDuplicatePairs", "sourceBankReview", "รีเช็คธนาคารต้นทาง", "sourceBankReviewCards", "ข้อมูลใบซ้ำ", "ข้อมูลต้นฉบับ", "original_reference_no", "ยกเลิกการนับซ้ำใบนี้"]:
    assert marker in html, marker
for forbidden in ["id <code>", "ใบซ้ำ <code>", "ใบต้นฉบับ <code>"]:
    assert forbidden not in html, forbidden

print("ok: duplicate pairs and source-bank review dashboard")
