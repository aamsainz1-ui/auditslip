#!/usr/bin/env python3
"""Guard: high-throughput Auditslip uses durable DB queue + worker job processing."""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "auditslip_bot.py"
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-worker-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-worker-export-")))
os.environ["AUDITSLIP_MAX_SLIPS_PER_POLL"] = "100"
os.environ["AUDITSLIP_OCR_WORKERS"] = "4"
os.environ["AUDITSLIP_REPLY_ON_QUEUE"] = "0"
os.environ["AUDITSLIP_REPLY_ON_RESULT"] = "1"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

spec = importlib.util.spec_from_file_location("auditslip_bot", MODULE)
assert spec is not None
app = importlib.util.module_from_spec(spec)
sys.modules["auditslip_bot"] = app
assert spec.loader is not None
spec.loader.exec_module(app)

assert app.MAX_SLIPS_PER_POLL >= 100
assert app.OCR_WORKERS >= 4
assert app.REPLY_ON_QUEUE is False

class FakeBot(app.AuditslipBot):
    def __init__(self):
        super().__init__(token="TEST_TOKEN", db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True)
        self.replies = []

    def reply(self, chat_id, text, reply_to_message_id=None):
        self.replies.append((chat_id, text, reply_to_message_id))

    def download_file(self, file_id):
        tmp = Path(tempfile.mkdtemp(prefix="auditslip-worker-img-")) / "slip.jpg"
        tmp.write_bytes(b"fake-image")
        return tmp, "image/jpeg"

bot = FakeBot()
bot.init_db()

msg = {
    "message_id": 101,
    "chat": {"id": "CHAT1", "title": "Audit Room"},
    "from": {"id": "U1", "first_name": "Alice"},
    "photo": [{"file_id": "FILE101"}],
}

# process_image_message must enqueue only; OCR is not called inline.
def should_not_call_inline(*args, **kwargs):
    raise AssertionError("OCR must not run inside Telegram polling/ingest")

app.ocr_extract = should_not_call_inline
bot.process_image_message(9001, msg)

with sqlite3.connect(os.environ["AUDITSLIP_DB"]) as conn:
    conn.row_factory = sqlite3.Row
    slip = conn.execute("SELECT * FROM slips WHERE chat_id='CHAT1' AND message_id=101").fetchone()
    job = conn.execute("SELECT * FROM ocr_jobs WHERE chat_id='CHAT1' AND message_id=101").fetchone()

assert slip is not None and slip["status"] == "queued", dict(slip) if slip else None
assert job is not None and job["status"] == "queued", dict(job) if job else None
assert bot.replies == [], "queue enqueue should be silent by default to avoid 3000/day noise"

# Worker path: claim + OCR + final success reply with captured total.
def fake_ocr(path, mime):
    return "gemini", {
        "slip_date_display": "22/05/26",
        "slip_date_iso": "2026-05-22",
        "slip_time": "12:34",
        "transferor_name": "คุณเอ",
        "recipient_name": "ร้านค้า",
        "amount": 1234.0,
        "fee": 0.0,
        "reference_no": "REF101",
        "confidence": 0.98,
        "ocr_provider": "gemini",
        "ocr_model": "gemini-2.5-flash",
        "raw_text": "amount 1234",
    }

app.ocr_extract = fake_ocr
claimed = bot.claim_ocr_job("worker-1")
assert claimed is not None, "worker should claim queued job"
bot.process_ocr_job(claimed, worker_id="worker-1")

with sqlite3.connect(os.environ["AUDITSLIP_DB"]) as conn:
    conn.row_factory = sqlite3.Row
    slip = conn.execute("SELECT * FROM slips WHERE chat_id='CHAT1' AND message_id=101").fetchone()
    job = conn.execute("SELECT * FROM ocr_jobs WHERE chat_id='CHAT1' AND message_id=101").fetchone()

assert slip["status"] == "success", dict(slip)
assert slip["amount"] == 1234.0, dict(slip)
assert job["status"] == "done", dict(job)
assert any("ยอดรวมที่จับได้" in text and "1,234.00" in text for _, text, _ in bot.replies), bot.replies

print("ok: Auditslip durable OCR queue + worker pool")
