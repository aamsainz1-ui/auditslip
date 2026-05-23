#!/usr/bin/env python3
"""Guard: Auditslip dashboard exposes accounting + queue metrics without secrets."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-dash-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-dash-export-")))
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True)
bot.init_db()
bot.save_slip({
    "id": "S1",
    "chat_id": "CHAT1",
    "chat_title": "Audit Room",
    "message_id": 1,
    "file_id": "FILE1",
    "sender_name": "Alice",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:00",
    "transferor_name": "คุณเอ",
    "amount": 100.0,
    "confidence": 0.99,
})
bot.save_slip({
    "id": "U1",
    "chat_id": "CHAT1",
    "chat_title": "Audit Room",
    "message_id": 2,
    "file_id": "FILE2",
    "sender_name": "Bob",
    "status": "unclear",
    "error": "missing amount",
})
bot.enqueue_ocr_job({
    "id": "Q1",
    "update_id": 10,
    "chat_id": "CHAT1",
    "chat_title": "Audit Room",
    "message_id": 3,
    "file_id": "FILE3",
    "sender_name": "Queue User",
}, "image/jpeg")

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snapshot = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]))
assert snapshot["totals"]["open_success_count"] == 1, snapshot
assert snapshot["totals"]["open_success_amount"] == 100.0, snapshot
assert snapshot["jobs"]["queued"] == 1, snapshot
assert snapshot["slip_statuses"]["unclear"] == 1, snapshot
assert snapshot["chats"][0]["chat_id"] == "CHAT1", snapshot
html = Dash.render_dashboard_html("test-token")
assert "Auditslip Dashboard" in html
assert "api/summary" in html
assert "sk-" not in html
print("ok: Auditslip dashboard metrics")
