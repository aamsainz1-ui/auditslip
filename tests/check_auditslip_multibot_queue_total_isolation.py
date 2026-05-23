#!/usr/bin/env python3
"""Guard: same chat id across multiple Telegram bots never mixes queue, totals, or commands."""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-multibot-isolation-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-multibot-isolation-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot1 = bot_mod.AuditslipBot(token="TOKEN1", db_path=db_path, dry_run=True, bot_key="bot1", company_name="บริษัท 1")
bot2 = bot_mod.AuditslipBot(token="TOKEN2", db_path=db_path, dry_run=True, bot_key="bot2", company_name="บริษัท 2")
bot1.init_db()
bot2.init_db()

base = {
    "chat_id": "SAME_CHAT",
    "chat_title": "Shared Telegram Group Id Fixture",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:00",
    "transferor_name": "คุณเอ",
    "recipient_name": "ร้านค้า",
    "from_bank": "SCB",
    "to_bank": "KBANK",
    "confidence": 0.99,
}

bot1.save_slip({**base, "id": "BOT1_SUCCESS", "bot_key": "bot1", "company_name": "บริษัท 1", "message_id": 11, "file_id": "FILE_BOT1_SUCCESS", "amount": 100.0})
bot2.save_slip({**base, "id": "BOT2_SUCCESS", "bot_key": "bot2", "company_name": "บริษัท 2", "message_id": 22, "file_id": "FILE_BOT2_SUCCESS", "amount": 900.0})
bot2.save_slip({**base, "id": "BOT2_UNCLEAR", "bot_key": "bot2", "company_name": "บริษัท 2", "message_id": 23, "file_id": "FILE_BOT2_UNCLEAR", "amount": 901.0, "status": "unclear", "error": "fixture unclear"})

job1 = bot1.enqueue_ocr_job({**base, "id": "BOT1_QUEUE", "bot_key": "bot1", "company_name": "บริษัท 1", "update_id": 101, "message_id": 101, "file_id": "FILE_BOT1_QUEUE"})
job2 = bot2.enqueue_ocr_job({**base, "id": "BOT2_QUEUE", "bot_key": "bot2", "company_name": "บริษัท 2", "update_id": 202, "message_id": 202, "file_id": "FILE_BOT2_QUEUE"})

# In-memory workers may share one SQLite DB, but each bot worker must claim only its own bot_key queue.
claimed1 = bot1.claim_ocr_job("bot1-worker")
assert claimed1 and claimed1["job_id"] == job1 and claimed1["bot_key"] == "bot1", dict(claimed1) if claimed1 else None
claimed2 = bot2.claim_ocr_job("bot2-worker")
assert claimed2 and claimed2["job_id"] == job2 and claimed2["bot_key"] == "bot2", dict(claimed2) if claimed2 else None
assert bot1.claim_ocr_job("bot1-worker-again") is None
assert bot2.claim_ocr_job("bot2-worker-again") is None

summary1 = bot1.summary_by_transferor("SAME_CHAT", "open")
summary2 = bot2.summary_by_transferor("SAME_CHAT", "open")
assert summary1["total_count"] == 1 and summary1["total_amount"] == 100.0, summary1
assert summary2["total_count"] == 1 and summary2["total_amount"] == 900.0, summary2

# Bot commands must be filtered by bot_key too, not only chat_id.
queue1 = bot1.queue_text("SAME_CHAT")
assert "BOT1_QUEUE" in queue1, queue1
assert "BOT2_QUEUE" not in queue1 and "BOT2_UNCLEAR" not in queue1, queue1
stats1 = bot1.stats_text("SAME_CHAT")
assert "success: 1" in stats1 and "success: 2" not in stats1, stats1
assert bot1.reprocess_latest("SAME_CHAT", "BOT2_UNCLEAR") == "ไม่พบรายการที่ต้อง reprocess ค่ะ"

# Destructive clear must only clear the current bot_key's rows for that chat.
result = bot1.clear_chat("SAME_CHAT")
assert result["slips"] >= 1, result
with sqlite3.connect(db_path) as conn:
    conn.row_factory = sqlite3.Row
    bot2_rows = conn.execute("SELECT COUNT(*) AS count FROM slips WHERE chat_id='SAME_CHAT' AND COALESCE(bot_key,'default')='bot2'").fetchone()["count"]
assert bot2_rows >= 1, bot2_rows

# Dashboard/API snapshots are also scoped by bot_key.
dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snap2 = Dash.dashboard_snapshot(db_path, chat_id="SAME_CHAT", bot_key="bot2", scope="open")
assert snap2["selected_bot_key"] == "bot2", snap2
assert snap2["totals"]["selected_success_count"] == 1, snap2["totals"]
assert snap2["totals"]["selected_success_amount"] == 900.0, snap2["totals"]
assert all(row.get("bot_key") == "bot2" for row in snap2["recent"]), snap2["recent"]

print("ok: multibot queue, totals, commands, and dashboard are isolated by bot_key")
