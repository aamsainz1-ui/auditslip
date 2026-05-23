#!/usr/bin/env python3
"""Guard: dashboard exposes selected-scope totals split by visible slip date."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-date-agg-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-date-agg-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True)
bot.init_db()

def slip(idx: int, display_date: str, iso_date: str, amount: float, duplicate: int = 0) -> None:
    bot.save_slip({
        "id": f"D{idx}",
        "chat_id": "CHAT1",
        "chat_title": "Audit Room",
        "message_id": idx,
        "file_id": f"FILE{idx}",
        "sender_name": "Uploader",
        "status": "success",
        "slip_date_display": display_date,
        "slip_date_iso": iso_date,
        "slip_time": f"09:{idx:02d}",
        "transferor_name": "จรัญ",
        "from_bank": "SCB",
        "amount": amount,
        "is_duplicate": duplicate,
    })

slip(1, "22/05/26", "2026-05-22", 100.0)
slip(2, "22/05/26 12:34", "2026-05-22", 200.0)
slip(3, "21/05/26", "2026-05-21", 50.0)
slip(4, "22/05/26 23:59", "2026-05-22", 999.0, duplicate=1)

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snapshot = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]), chat_id="CHAT1", scope="open")
by_date = {row["date"]: row for row in snapshot["by_date"]}
assert by_date["22/05/26"]["count"] == 2, by_date
assert by_date["22/05/26"]["amount"] == 300.0, by_date
assert by_date["21/05/26"]["count"] == 1, by_date
assert by_date["21/05/26"]["amount"] == 50.0, by_date
html = Dash.render_dashboard_html("test-token")
assert "byDate" in html and "ยอดแยกตามวันที่" in html, html
print("ok: dashboard date aggregates use visible slip date")
