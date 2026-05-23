#!/usr/bin/env python3
"""Guard: high-volume dashboard normalization helpers cache repeated work.

Open-period snapshots call display_bank/date_bucket tens of thousands of times on
production data. Repeated identical banks/dates should not rebuild alias maps or
re-parse the same date on every row.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot1:BOT_TOKEN:บริษัท 1"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-hotpath-cache-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-hotpath-cache-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert spec and spec.loader
Dash = importlib.util.module_from_spec(spec)
sys.modules["auditslip_dashboard"] = Dash
spec.loader.exec_module(Dash)

# display_bank should normalize the first identical value, then hit a cache.
orig_bank_key = getattr(Dash, "bank_key")
bank_calls = {"count": 0}

def counted_bank_key(value):
    bank_calls["count"] += 1
    return orig_bank_key(value)

if hasattr(Dash.display_bank, "cache_clear"):
    Dash.display_bank.cache_clear()
setattr(Dash, "bank_key", counted_bank_key)
for _ in range(100):
    assert Dash.display_bank("SCB") == "SCB"
assert bank_calls["count"] <= 5, f"display_bank recalculated {bank_calls['count']} times for the same value"
setattr(Dash, "bank_key", orig_bank_key)

# date_bucket should parse each identical display/ISO pair once.
orig_normalize_date_parts = getattr(Dash, "normalize_date_parts")
date_calls = {"count": 0}

def counted_normalize_date_parts(value):
    date_calls["count"] += 1
    return orig_normalize_date_parts(value)

if hasattr(Dash.date_bucket, "cache_clear"):
    Dash.date_bucket.cache_clear()
setattr(Dash, "normalize_date_parts", counted_normalize_date_parts)
for _ in range(100):
    assert Dash.date_bucket("23/05/26", "2026-05-23") == ("2026-05-23", "23/05/26", "2026-05-23")
assert date_calls["count"] <= 4, f"date_bucket parsed {date_calls['count']} times for the same date"
setattr(Dash, "normalize_date_parts", orig_normalize_date_parts)

print("ok: dashboard hot-path bank/date normalization caches repeated work")
