#!/usr/bin/env python3
"""Guard: daily limits are evaluated per transferor account per day, not as one cross-day total."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-daily-account-limit-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-daily-account-limit-export-")))
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

def slip(idx: int, *, iso: str, display: str, amount: float, account: str = "111-xxx-222") -> None:
    bot.save_slip({
        "id": f"DL{idx}",
        "chat_id": "CHAT1",
        "chat_title": "Audit Room",
        "message_id": idx,
        "file_id": f"FILE{idx}",
        "sender_name": "Uploader",
        "status": "success",
        "slip_date_display": display,
        "slip_date_iso": iso,
        "slip_time": f"10:{idx:02d}",
        "transferor_name": "คุณเอ",
        "issuer_bank": "KBANK",
        "from_bank": "กสิกรไทย",
        "from_account": account,
        "to_bank": "SCB",
        "amount": amount,
        "confidence": 0.99,
    })

# Same account on two different days. The 300 limit must reset each day.
slip(1, iso="2026-05-22", display="22/05/26", amount=100.0)
slip(2, iso="2026-05-22", display="22/05/26", amount=250.0)
slip(3, iso="2026-05-23", display="23/05/26", amount=250.0)
# Same day but different account must be evaluated separately.
slip(4, iso="2026-05-22", display="22/05/26", amount=280.0, account="999-xxx-000")
# Real OCR/display data can mix Thai month labels and Buddhist-era ISO years.
# These rows must still normalize to AD dates and keep all 22 May rows together above 21 May.
slip(5, iso="2569-05-21", display="21 พ/ค/2569", amount=3700.0, account="222-xxx-111")
slip(6, iso="", display="22 พ/ค/2569", amount=128551.0, account="333-xxx-222")

# Same account split across two days where each day is under the limit.
# The period total exceeds 200, but it must not be flagged as over-limit.
slip(7, iso="2026-05-22", display="22/05/26", amount=150.0, account="777-xxx-888")
slip(8, iso="2026-05-23", display="23/05/26", amount=180.0, account="777-xxx-888")

# Company rows should stay in operator order (บริษัท 1 -> 6) within each day,
# not jump around by amount.
for company_no, amount in [(6, 6000.0), (3, 3000.0), (1, 100.0), (5, 5000.0), (2, 2000.0), (4, 4000.0)]:
    bot.save_slip({
        "id": f"SORT{company_no}",
        "bot_key": "default",
        "company_name": f"บริษัท {company_no}",
        "chat_id": "CHAT1",
        "chat_title": f"บริษัท {company_no} ถอน",
        "message_id": 100 + company_no,
        "file_id": f"FILE_SORT_{company_no}",
        "sender_name": "Uploader",
        "status": "success",
        "slip_date_display": "24/05/26",
        "slip_date_iso": "2026-05-24",
        "slip_time": f"11:{company_no:02d}",
        "transferor_name": f"ลูกค้า {company_no}",
        "issuer_bank": "KBANK",
        "from_bank": "KBANK",
        "from_account": f"SORT-ACC-{company_no}",
        "to_bank": "SCB",
        "amount": amount,
        "confidence": 0.99,
    })

# Bot-level limit set from the all-company overview must still render in the
# all-company overview after reload. This mirrors the mobile operator flow:
# overview (__all__) -> row has bot_key -> save as bot:<bot_key> -> reload overview.
bot.save_slip({
    "id": "GLOBAL_BOT_LIMIT",
    "bot_key": "bot6",
    "company_name": "บริษัท 6",
    "chat_id": "CHAT6",
    "chat_title": "บริษัท 6 ถอน",
    "message_id": 606,
    "file_id": "FILE_GLOBAL_BOT_LIMIT",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "25/05/26",
    "slip_date_iso": "2026-05-25",
    "slip_time": "12:06",
    "transferor_name": "สหรัฐ ท.",
    "issuer_bank": "SCB",
    "from_bank": "SCB",
    "from_account": "xxx-xxx052-2",
    "to_bank": "KBANK",
    "amount": 1234.0,
    "confidence": 0.99,
})

# Duplicate slips must not count toward daily limit usage.
bot.save_slip({
    "id": "DL_DUP",
    "chat_id": "CHAT1",
    "chat_title": "Audit Room",
    "message_id": 9,
    "file_id": "FILE_DUP",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:09",
    "transferor_name": "คุณเอ",
    "issuer_bank": "KBANK",
    "from_bank": "KBANK",
    "from_account": "111-xxx-222",
    "to_bank": "SCB",
    "amount": 999.0,
    "is_duplicate": 1,
})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snapshot = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]), chat_id="CHAT1", scope="all")
by_transferor = {row["account"]: row for row in snapshot["by_transferor"]}
limit_key = by_transferor["111-xxx-222"]["limit_key"]
Dash.save_account_limit(Path(os.environ["AUDITSLIP_DB"]), "CHAT1", limit_key, "คุณเอ", "KBANK", "111-xxx-222", 300.0)
split_limit_key = by_transferor["777-xxx-888"]["limit_key"]
Dash.save_account_limit(Path(os.environ["AUDITSLIP_DB"]), "CHAT1", split_limit_key, "คุณเอ", "KBANK", "777-xxx-888", 200.0)

global_snapshot_before = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]), bot_key="__all__", scope="all")
global_rows_before = {(r["bot_key"], r["account"]): r for r in global_snapshot_before["by_account_day"]}
global_bot_row_before = global_rows_before[("bot6", "xxx-xxx052-2")]
assert global_bot_row_before["daily_limit"] == 200000.0, global_bot_row_before  # SCB default before override
Dash.save_account_limit(Path(os.environ["AUDITSLIP_DB"]), "bot:bot6", global_bot_row_before["limit_key"], "สหรัฐ ท.", "SCB", "xxx-xxx052-2", 100000.0)

global_snapshot = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]), bot_key="__all__", scope="all")
global_rows = {(r["bot_key"], r["account"]): r for r in global_snapshot["by_account_day"]}
global_bot_row = global_rows[("bot6", "xxx-xxx052-2")]
assert global_bot_row["daily_limit"] == 100000.0, global_bot_row
assert global_bot_row["remaining_amount"] == 98766.0, global_bot_row

snapshot = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]), chat_id="CHAT1", scope="all")
summary_rows = {row["account"]: row for row in snapshot["by_transferor"]}
summary = summary_rows["111-xxx-222"]
assert summary["amount"] == 600.0, summary
assert summary["peak_daily_amount"] == 350.0, summary
assert summary["peak_daily_date"] == "22/05/26", summary
assert summary["remaining_amount"] == -50.0, summary
assert summary["over_limit"] is True, summary
split_summary = summary_rows["777-xxx-888"]
assert split_summary["amount"] == 330.0, split_summary
assert split_summary["peak_daily_amount"] == 180.0, split_summary
assert split_summary["remaining_amount"] == 20.0, split_summary
assert split_summary["over_limit"] is False, split_summary
rows = {(r["date_key"], r["account"]): r for r in snapshot["by_account_day"]}
assert rows[("2026-05-22", "111-xxx-222")]["amount"] == 350.0, rows
assert rows[("2026-05-22", "111-xxx-222")]["daily_limit"] == 300.0, rows
assert rows[("2026-05-22", "111-xxx-222")]["remaining_amount"] == -50.0, rows
assert rows[("2026-05-22", "111-xxx-222")]["over_limit"] is True, rows
assert rows[("2026-05-23", "111-xxx-222")]["amount"] == 250.0, rows
assert rows[("2026-05-23", "111-xxx-222")]["remaining_amount"] == 50.0, rows
assert rows[("2026-05-23", "111-xxx-222")]["over_limit"] is False, rows
assert rows[("2026-05-22", "999-xxx-000")]["amount"] == 280.0, rows
assert rows[("2026-05-22", "999-xxx-000")]["daily_limit"] == 0.0, rows
assert rows[("2026-05-21", "222-xxx-111")]["amount"] == 3700.0, rows
assert rows[("2026-05-22", "333-xxx-222")]["amount"] == 128551.0, rows
sort_day_companies = [r["company_name"] for r in snapshot["by_account_day"] if r["date_key"] == "2026-05-24" and str(r["account"]).startswith("SORT-ACC-")]
assert sort_day_companies == [f"บริษัท {i}" for i in range(1, 7)], sort_day_companies

ordered_keys = [r["date_key"] for r in snapshot["by_account_day"]]
assert "2569-05-21" not in ordered_keys, ordered_keys
seen_older_date = False
for key in ordered_keys:
    if key == "2026-05-21":
        seen_older_date = True
    if seen_older_date:
        assert key != "2026-05-22", ordered_keys

html = Dash.render_dashboard_html("test-token")
for marker in ["byAccountDay", "วงเงินรายวันต่อบัญชี", "ยอดวันนี้", "วงเงิน/วัน", "dailyAccountLimitTable", "ตั้งวงเงินจากยอดรายวัน", "เหลือ/เกินวันนี้"]:
    assert marker in html, marker
for forbidden in ["ยอดวันนั้น", "เหลือ/เกินวันนั้น", "วันนั้น", "ยอดรวมช่วง", "เหลือ/เกินจากยอดรวม"]:
    assert forbidden not in html, forbidden

print("ok: daily account limits reset by date and account")
