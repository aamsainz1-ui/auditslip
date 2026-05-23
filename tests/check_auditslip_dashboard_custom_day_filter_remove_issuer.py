#!/usr/bin/env python3
"""Guard: operator can select a company + custom slip date and issuer-bank panel is not loaded/rendered."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot1:BOT_TOKEN:บริษัท 1,bot2:BOT_TOKEN:บริษัท 2"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-custom-day-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-custom-day-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot1 = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="bot1", company_name="บริษัท 1")
bot1.init_db()
bot2 = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="bot2", company_name="บริษัท 2")
bot2.init_db()

def save(bot, slip_id: str, bot_key: str, company: str, date_display: str, date_iso: str, amount: float) -> None:
    bot.save_slip({
        "id": slip_id,
        "bot_key": bot_key,
        "company_name": company,
        "chat_id": f"CHAT_{bot_key}",
        "chat_title": f"{company} ฝาก",
        "message_id": int(amount),
        "file_id": f"FILE_{slip_id}",
        "sender_name": "Uploader",
        "status": "success",
        "slip_date_display": date_display,
        "slip_date_iso": date_iso,
        "slip_time": "10:00",
        "transferor_name": "ลูกค้า",
        "recipient_name": company,
        "from_bank": "SCB",
        "from_account": "CUST",
        "to_bank": "KBANK",
        "to_account": f"ACC-{bot_key}",
        "issuer_bank": "KBANK",
        "amount": amount,
        "reference_no": slip_id,
    })

save(bot1, "BOT1_DAY22", "bot1", "บริษัท 1", "22/05/26", "2026-05-22", 100.0)
save(bot1, "BOT1_DAY21", "bot1", "บริษัท 1", "21/05/26", "2026-05-21", 200.0)
save(bot2, "BOT2_DAY22", "bot2", "บริษัท 2", "22/05/26", "2026-05-22", 300.0)

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snap = Dash.dashboard_snapshot(db_path, bot_key="bot1", flow_type="deposit", scope="2026-05-22")
assert snap["selected_bot_key"] == "bot1", snap
assert snap["scope"] == "2026-05-22", snap
assert snap["totals"]["selected_success_count"] == 1, snap["totals"]
assert snap["totals"]["selected_success_amount"] == 100.0, snap["totals"]
assert [row["date"] for row in snap["by_date"]] == ["22/05/26"], snap["by_date"]
assert [row["id"] for row in snap["recent"]] == ["BOT1_DAY22"], snap["recent"]
assert {(row["bot_key"], row["date_key"]) for row in snap["company_account_daily"]} == {("bot1", "2026-05-22")}, snap["company_account_daily"]
assert "by_issuer_bank" not in snap, snap.keys()

html = Dash.render_dashboard_html("test-token")
for marker in ["customDateFilter", "เลือกวันที่เดียว", "currentDate", "customDateFilter", "customDateEl.addEventListener", "scope: currentScope"]:
    assert marker in html, marker
for removed in ["byIssuerBank", "by_issuer_bank", "ยอดแยกตามธนาคารบนสลิป", "ธนาคารบนสลิป"]:
    assert removed not in html, removed

print("ok: custom company-day filter scopes all dashboard panels and issuer-bank panel is removed")
