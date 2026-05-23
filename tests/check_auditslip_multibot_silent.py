#!/usr/bin/env python3
"""Guard: Auditslip can ingest multiple Telegram bots silently, one bot/company/group per config."""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "DEFAULT_TEST_TOKEN"
os.environ["BOT_TOKEN_1"] = "TOKEN_ONE"
os.environ["BOT_TOKEN_2"] = "TOKEN_TWO"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot1:BOT_TOKEN_1:บริษัท 1,bot2:BOT_TOKEN_2:บริษัท 2"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-multibot-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-multibot-export-")))
os.environ["AUDITSLIP_REPLY_ON_QUEUE"] = "0"
os.environ["AUDITSLIP_REPLY_ON_RESULT"] = "0"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert spec and spec.loader
app = importlib.util.module_from_spec(spec)
sys.modules["auditslip_bot"] = app
spec.loader.exec_module(app)

configs = app.telegram_bot_configs()
assert [c["bot_key"] for c in configs] == ["bot1", "bot2"], configs
assert configs[0]["token"] == "TOKEN_ONE" and configs[0]["company_name"] == "บริษัท 1", configs
assert configs[1]["token_env"] == "BOT_TOKEN_2", configs
assert app.REPLY_ON_RESULT is False

class SilentBot(app.AuditslipBot):
    def __init__(self, *, token: str, bot_key: str, company_name: str):
        super().__init__(token=token, db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True, bot_key=bot_key, company_name=company_name, reply_on_result=False)
        self.replies = []

    def reply(self, chat_id, text, reply_to_message_id=None):
        self.replies.append((chat_id, text, reply_to_message_id))

    def download_file(self, file_id):
        tmp = Path(tempfile.mkdtemp(prefix=f"auditslip-{self.bot_key}-img-")) / "slip.jpg"
        tmp.write_bytes(b"fake-image")
        return tmp, "image/jpeg"

bot1 = SilentBot(token="TOKEN_ONE", bot_key="bot1", company_name="บริษัท 1")
bot2 = SilentBot(token="TOKEN_TWO", bot_key="bot2", company_name="บริษัท 2")
bot1.init_db()
bot2.init_db()

update = {
    "update_id": 77,
    "message": {
        "message_id": 501,
        "chat": {"id": "GROUP_A", "title": "กลุ่มจับยอด"},
        "from": {"id": "U1", "first_name": "Alice"},
        "photo": [{"file_id": "FILE501"}],
    },
}
bot1.process_update(update)
bot2.process_update(update)

with sqlite3.connect(os.environ["AUDITSLIP_DB"]) as conn:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT bot_key, company_name, status FROM slips WHERE chat_id='GROUP_A' ORDER BY bot_key").fetchall()
    jobs = conn.execute("SELECT bot_key, company_name, status FROM ocr_jobs WHERE chat_id='GROUP_A' ORDER BY bot_key").fetchall()

assert [(r["bot_key"], r["company_name"], r["status"]) for r in rows] == [("bot1", "บริษัท 1", "queued"), ("bot2", "บริษัท 2", "queued")], [dict(r) for r in rows]
assert [(j["bot_key"], j["company_name"], j["status"]) for j in jobs] == [("bot1", "บริษัท 1", "queued"), ("bot2", "บริษัท 2", "queued")], [dict(j) for j in jobs]
assert bot1.replies == [] and bot2.replies == [], "slip ingestion should not reply in groups"
assert bot1.already_processed(77) is True and bot2.already_processed(77) is True

# Each bot worker must only claim its own jobs because Telegram file_id download needs that bot's token.
def fake_ocr(path, mime):
    return "gemini", {
        "slip_date_display": "22/05/26",
        "slip_date_iso": "2026-05-22",
        "slip_time": "12:34",
        "transferor_name": "คุณเอ",
        "recipient_name": "ร้านค้า",
        "amount": 222.0,
        "fee": 0.0,
        "reference_no": "REF501",
        "confidence": 0.98,
        "raw_text": "amount 222",
    }

setattr(app, "ocr_extract", fake_ocr)
job1 = bot1.claim_ocr_job("worker-bot1")
assert job1 is not None and job1["bot_key"] == "bot1", dict(job1) if job1 else None
bot1.process_ocr_job(job1, worker_id="worker-bot1")
job2 = bot2.claim_ocr_job("worker-bot2")
assert job2 is not None and job2["bot_key"] == "bot2", dict(job2) if job2 else None
bot2.process_ocr_job(job2, worker_id="worker-bot2")
assert bot1.replies == [] and bot2.replies == [], "OCR results should be silent when AUDITSLIP_REPLY_ON_RESULT=0"

print("ok: multibot silent ingestion")
