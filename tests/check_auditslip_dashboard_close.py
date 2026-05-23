#!/usr/bin/env python3
"""Guard: dashboard can close/open-clear the selected chat using the same settlement logic as /close."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-dash-close-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-dash-close-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True)
bot.init_db()
for idx, amount in enumerate([100.0, 200.0], start=1):
    bot.save_slip({
        "id": f"S{idx}",
        "chat_id": "CHAT1",
        "chat_title": "Audit Room",
        "message_id": idx,
        "file_id": f"FILE{idx}",
        "sender_name": "Alice",
        "status": "success",
        "slip_date_display": "22/05/26",
        "slip_date_iso": "2026-05-22",
        "slip_time": f"10:0{idx}",
        "transferor_name": "คุณเอ",
        "amount": amount,
        "confidence": 0.99,
    })

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

before = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]))
assert before["totals"]["open_success_amount"] == 300.0, before
result = Dash.dashboard_close_period(Path(os.environ["AUDITSLIP_DB"]), "CHAT1", "dashboard-test")
assert result["ok"] is True, result
assert result["closed_count"] == 2, result
assert result["total_amount"] == 300.0, result
after = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]))
assert after["totals"]["open_success_amount"] == 0.0, after
assert after["totals"]["open_success_count"] == 0, after
html = Dash.render_dashboard_html("test-token")
assert "Close / เคลียร์ยอด" in html
assert "/api/close" in html
print("ok: dashboard close clears open totals via settlement")
