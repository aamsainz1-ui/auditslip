#!/usr/bin/env python3
"""Guard: duplicate detection requires the full slip signature, not partial matches."""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-dupe-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-dupe-export-")))

spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert spec and spec.loader
bot_mod = importlib.util.module_from_spec(spec)
sys.modules["auditslip_bot"] = bot_mod
spec.loader.exec_module(bot_mod)

bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True)
bot.init_db()
base = {
    "chat_id": "CHAT1",
    "chat_title": "Audit Room",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:10",
    "transferor_name": "คุณเอ",
    "recipient_name": "ร้านค้า",
    "amount": 1234.0,
    "reference_no": "REF-ABC-123",
    "confidence": 0.99,
}
bot.save_slip({**base, "id": "FIRST", "message_id": 1, "file_id": "FILE1"})

# Any single mismatch must NOT be considered duplicate.
bot.save_slip({**base, "id": "DIFF_NAME", "message_id": 2, "file_id": "FILE2", "transferor_name": "คุณบี"})
bot.save_slip({**base, "id": "DIFF_RECIPIENT", "message_id": 3, "file_id": "FILE3", "recipient_name": "ร้านค้าอื่น"})
bot.save_slip({**base, "id": "DIFF_DATE", "message_id": 4, "file_id": "FILE4", "slip_date_display": "23/05/26", "slip_date_iso": "2026-05-23"})
bot.save_slip({**base, "id": "DIFF_AMOUNT", "message_id": 5, "file_id": "FILE5", "amount": 1235.0})
bot.save_slip({**base, "id": "DIFF_TIME", "message_id": 6, "file_id": "FILE6", "slip_time": "10:11"})
bot.save_slip({**base, "id": "DIFF_REF", "message_id": 7, "file_id": "FILE7", "reference_no": "REF-XYZ-999"})
bot.save_slip({**base, "id": "NO_REF", "message_id": 8, "file_id": "FILE8", "reference_no": ""})

# Only a full match: transferor + recipient + date + amount + time + reference is duplicate.
bot.save_slip({**base, "id": "SECOND", "message_id": 9, "file_id": "FILE9"})

with sqlite3.connect(os.environ["AUDITSLIP_DB"]) as conn:
    conn.row_factory = sqlite3.Row
    rows = {r["id"]: dict(r) for r in conn.execute("SELECT id, is_duplicate, duplicate_of FROM slips ORDER BY created_at, id")}

for slip_id in ["DIFF_NAME", "DIFF_RECIPIENT", "DIFF_DATE", "DIFF_AMOUNT", "DIFF_TIME", "DIFF_REF", "NO_REF"]:
    assert int(rows[slip_id]["is_duplicate"] or 0) == 0, rows[slip_id]
    assert not rows[slip_id]["duplicate_of"], rows[slip_id]

assert int(rows["SECOND"]["is_duplicate"] or 0) == 1, rows["SECOND"]
assert rows["SECOND"]["duplicate_of"] == "FIRST", rows["SECOND"]
print("ok: duplicate detection requires exact name/date/amount/time/ref signature")
