#!/usr/bin/env python3
"""Guard: dashboard can search an account and show the individual slip images/rows for audit."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A,botB:BOT_TOKEN:บริษัท B"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-account-slip-search-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-account-slip-search-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot_a = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="botA", company_name="บริษัท A")
bot_a.init_db()
bot_b = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="botB", company_name="บริษัท B")
bot_b.init_db()

def save(bot, slip_id: str, bot_key: str, company: str, chat_id: str, title: str, date_display: str, date_iso: str, amount: float, from_account: str, to_account: str, ref: str, duplicate: int = 0) -> None:
    bot.save_slip({
        "id": slip_id,
        "bot_key": bot_key,
        "company_name": company,
        "chat_id": chat_id,
        "chat_title": title,
        "message_id": int(ref[-2:]) if ref[-2:].isdigit() else 1,
        "file_id": f"FILE_{slip_id}",
        "sender_name": "Uploader",
        "status": "success",
        "slip_date_display": date_display,
        "slip_date_iso": date_iso,
        "slip_time": "10:00",
        "transferor_name": "ลูกค้า A",
        "recipient_name": company,
        "from_bank": "SCB",
        "from_account": from_account,
        "to_bank": "KBANK",
        "to_account": to_account,
        "account_name": company,
        "amount": amount,
        "reference_no": ref,
        "is_duplicate": duplicate,
    })

save(bot_a, "A_DEP_1", "botA", "บริษัท A", "A_DEP", "บริษัท A ฝาก/เติมมือ", "22/05/26", "2026-05-22", 100.0, "CUST-001", "A-ACC-001", "REF01")
save(bot_a, "A_DEP_2", "botA", "บริษัท A", "A_DEP", "บริษัท A ฝาก/เติมมือ", "22/05/26", "2026-05-22", 50.0, "CUST-002", "A-ACC-001", "REF02")
save(bot_a, "A_DEP_OLD", "botA", "บริษัท A", "A_DEP", "บริษัท A ฝาก/เติมมือ", "21/05/26", "2026-05-21", 999.0, "CUST-OLD", "A-ACC-001", "REF03")
save(bot_a, "A_DUP", "botA", "บริษัท A", "A_DEP", "บริษัท A ฝาก/เติมมือ", "22/05/26", "2026-05-22", 888.0, "CUST-DUP", "A-ACC-001", "REF04", duplicate=1)
save(bot_b, "B_DEP", "botB", "บริษัท B", "B_DEP", "บริษัท B ฝาก", "22/05/26", "2026-05-22", 700.0, "CUST-B", "A-ACC-001", "REF05")
save(bot_a, "A_OTHER", "botA", "บริษัท A", "A_DEP", "บริษัท A ฝาก/เติมมือ", "22/05/26", "2026-05-22", 12.0, "CUST-X", "A-ACC-999", "REF06")

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snap = Dash.dashboard_snapshot(db_path, bot_key="botA", flow_type="deposit", scope="2026-05-22", slip_search="A-ACC-001")
search = snap["account_slip_search"]
assert search["query"] == "A-ACC-001", search
assert search["count"] == 2, search
assert search["amount"] == 150.0, search
assert [r["id"] for r in search["rows"]] == ["A_DEP_2", "A_DEP_1"], search["rows"]
assert all(r["image_url"].startswith("/api/slip-image?id=") for r in search["rows"]), search["rows"]
assert all(r["bot_key"] == "botA" for r in search["rows"]), search["rows"]
assert all(r["status"] == "success" and not int(r.get("is_duplicate") or 0) for r in search["rows"]), search["rows"]
assert all(r["date_key"] == "2026-05-22" for r in search["rows"]), search["rows"]
assert {r["matched_side"] for r in search["rows"]} == {"to"}, search["rows"]

# Compact account-number search should work even when users omit punctuation/spaces.
snap_compact = Dash.dashboard_snapshot(db_path, bot_key="botA", flow_type="deposit", scope="2026-05-22", slip_search="AACC001")
assert snap_compact["account_slip_search"]["count"] == 2, snap_compact["account_slip_search"]

# Empty search should not dump every image-heavy slip into the auto-refresh payload.
snap_empty = Dash.dashboard_snapshot(db_path, bot_key="botA", flow_type="deposit", scope="2026-05-22", slip_search="")
assert snap_empty["account_slip_search"]["rows"] == [], snap_empty["account_slip_search"]

html = Dash.render_dashboard_html("test-token")
for marker in ["accountSlipSearch", "renderAccountSlipSearch", "ดูสลิปบัญชีนี้", "ค้นหารายการสลิปตามบัญชี", "data-account-search"]:
    assert marker in html, marker

print("ok: dashboard searches individual slip rows by account with images")
