#!/usr/bin/env python3
"""Guard: visible slip date wins over contradictory OCR-normalized ISO date."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-date-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert spec and spec.loader
bot_mod = importlib.util.module_from_spec(spec)
sys.modules["auditslip_bot"] = bot_mod
spec.loader.exec_module(bot_mod)


def norm(display: str, iso: str) -> dict:
    return bot_mod.normalize_record(
        {
            "slip_date_display": display,
            "slip_date_iso": iso,
            "slip_time": "12:34",
            "amount": "1,000.00",
            "transferor_name": "Tester",
            "recipient_name": "Company",
            "confidence": 0.99,
        }
    )

row = norm("22/05/26", "2022-05-22")
assert row["slip_date_display"] == "22/05/26", row
assert row["slip_date_iso"] == "2026-05-22", row

thai = norm("22 พ.ค. 2569", "2022-05-22")
assert thai["slip_date_display"] == "22 พ.ค. 2569", thai
assert thai["slip_date_iso"] == "2026-05-22", thai

iso_only = norm("", "2026-05-22")
assert iso_only["slip_date_display"] == "22/05/26", iso_only
assert iso_only["slip_date_iso"] == "2026-05-22", iso_only

print("ok: visible slip date takes precedence over bad OCR ISO date")
