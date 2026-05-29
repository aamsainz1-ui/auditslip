#!/usr/bin/env python3
"""Guard: OCR API cost is calculated from real token usage, not slip counts."""
from __future__ import annotations

import importlib.util
import math
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(tempfile.mkdtemp(prefix="auditslip-cost-tracking-")) / "auditslip.db"

os.environ["AUDITSLIP_DB"] = str(DB_PATH)
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-cost-export-")))
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot1:BOT_TOKEN:บริษัท 1"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
app = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = app
bot_spec.loader.exec_module(app)

# Gemini 2.5 Flash paid standard tier: input $0.30/M, output incl. thoughts $2.50/M.
gemini_cost = app.ocr_usage_cost_usd("gemini", "gemini-2.5-flash", input_tokens=700, output_tokens=40, thought_tokens=10)
assert math.isclose(gemini_cost, 0.000335, rel_tol=0, abs_tol=1e-12), gemini_cost

# OpenAI gpt-4o-mini: input $0.15/M, output $0.60/M. completion_tokens already includes reasoning.
openai_cost = app.ocr_usage_cost_usd("openai", "gpt-4o-mini", input_tokens=900, output_tokens=80, thought_tokens=12)
assert math.isclose(openai_cost, 0.000183, rel_tol=0, abs_tol=1e-12), openai_cost

bot = app.AuditslipBot(token="TEST_TOKEN", db_path=DB_PATH, dry_run=True, bot_key="bot1", company_name="บริษัท 1")
bot.init_db()
bot.save_slip(
    {
        "id": "COST-SLIP-1",
        "bot_key": "bot1",
        "company_name": "บริษัท 1",
        "chat_id": "CHAT1",
        "chat_title": "บริษัท 1 ถอน",
        "message_id": 1,
        "file_id": "FILE1",
        "status": "success",
        "slip_date_display": "24/05/69",
        "slip_date_iso": "2026-05-24",
        "amount": 123.0,
        "confidence": 0.99,
        "ocr_provider": "gemini",
        "ocr_model": "gemini-2.5-flash",
        "ocr_input_tokens": 700,
        "ocr_output_tokens": 40,
        "ocr_thought_tokens": 10,
        "ocr_total_tokens": 750,
    }
)

with sqlite3.connect(DB_PATH) as conn:
    conn.row_factory = sqlite3.Row
    cols = {row[1] for row in conn.execute("PRAGMA table_info(slips)").fetchall()}
    assert "ocr_cost_usd" in cols, cols
    assert "ocr_pricing_json" in cols, cols
    row = conn.execute("SELECT * FROM slips WHERE id='COST-SLIP-1'").fetchone()
    assert math.isclose(row["ocr_cost_usd"], 0.000335, rel_tol=0, abs_tol=1e-12), dict(row)
    assert "gemini-2.5-flash" in row["ocr_pricing_json"], dict(row)

usage = bot.usage_text("CHAT1", "all")
assert "$0.000335" in usage, usage
assert "ราคาโดยประมาณ" in usage, usage

spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert spec and spec.loader
Dash = importlib.util.module_from_spec(spec)
sys.modules["auditslip_dashboard"] = Dash
spec.loader.exec_module(Dash)

snapshot = Dash.dashboard_snapshot(DB_PATH, bot_key="bot1", scope="all", flow_type="withdraw")
provider_usage = snapshot["provider_usage"]
assert provider_usage, snapshot.keys()
assert math.isclose(provider_usage[0]["cost_usd"], 0.000335, rel_tol=0, abs_tol=1e-12), provider_usage

html = Dash.render_dashboard_html("test-token")
scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
script_text = "\n".join(scripts)
assert "['cost $','cost_usd']" in script_text, script_text[:1000]

print("ok: OCR API cost is estimated from recorded provider token usage")
