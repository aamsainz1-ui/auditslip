#!/usr/bin/env python3
"""Guard: durable OCR queue resumes after process/VPS restart without losing the claimed job."""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-resume-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-resume-export-")))

spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert spec and spec.loader
bot_mod = importlib.util.module_from_spec(spec)
sys.modules["auditslip_bot"] = bot_mod
spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True)
bot.init_db()
job_id = bot.enqueue_ocr_job({
    "id": "R1",
    "update_id": 101,
    "chat_id": "CHAT1",
    "chat_title": "Audit Room",
    "message_id": 11,
    "file_id": "FILE11",
    "sender_name": "Uploader",
}, "image/jpeg")
claimed = bot.claim_ocr_job("worker-before-restart")
assert claimed and claimed["job_id"] == job_id, claimed
assert claimed["status"] == "processing", claimed

# Fresh bot instance simulates a process/VPS restart. It must immediately make
# processing jobs claimable again, not wait for the stale timeout.
restarted = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True)
restarted.init_db()
resumed_count = restarted.resume_incomplete_ocr_jobs()
assert resumed_count == 1, resumed_count
reclaimed = restarted.claim_ocr_job("worker-after-restart")
assert reclaimed and reclaimed["job_id"] == job_id, reclaimed
assert reclaimed["status"] == "processing", reclaimed
assert reclaimed["locked_by"] == "worker-after-restart", reclaimed

# Re-saving the same slip id after a crash retry must not mark itself duplicate.
row = {
    "id": "R1",
    "chat_id": "CHAT1",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "12:00",
    "amount": 100,
    "reference_no": "REF-RETRY-1",
}
restarted.save_slip(row)
restarted.save_slip({**row, "amount": 100})
with sqlite3.connect(db_path) as conn:
    conn.row_factory = sqlite3.Row
    slip = conn.execute("SELECT is_duplicate, duplicate_of FROM slips WHERE id='R1'").fetchone()
assert int(slip["is_duplicate"] or 0) == 0, dict(slip)
assert not slip["duplicate_of"], dict(slip)
print("ok: OCR queue resumes after restart and self-upsert is not duplicate")
