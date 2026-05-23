#!/usr/bin/env python3
"""Guard: OCR should preserve the date text as printed on the slip for display."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"

spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert spec and spec.loader
bot_mod = importlib.util.module_from_spec(spec)
sys.modules["auditslip_bot"] = bot_mod
spec.loader.exec_module(bot_mod)

prompt = bot_mod.ocr_prompt()
assert "Preserve slip_date_display exactly as printed/visible on the slip" in prompt, prompt
record = bot_mod.normalize_record({
    "slip_date_display": "07/05/26",
    "slip_date_iso": "2026-05-07",
    "slip_time": "09:12",
    "amount": "7,000.00",
})
assert record["slip_date_display"] == "07/05/26", record

db_path = Path(tempfile.mkdtemp(prefix="auditslip-date-")) / "auditslip.db"
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True)
bot.init_db()
bot.save_slip({
    "id": "D1",
    "chat_id": "CHAT1",
    "status": "success",
    "slip_date_display": "07/05/26",
    "slip_date_iso": "2026-05-07",
    "slip_time": "09:12",
    "amount": 7000,
})
daily = bot.daily_summary("CHAT1", "all")
assert daily[0]["day"] == "07/05/26", daily[0]["day"]
print("ok: slip date display preserves visible slip format")
