#!/usr/bin/env python3
"""Guard: cross-company account search/summary is for withdrawal slips only, not deposit/top-up."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A,botB:BOT_TOKEN:บริษัท B"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-cross-withdraw-only-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-cross-withdraw-only-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
Bot = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = Bot
bot_spec.loader.exec_module(Bot)

db_path = Path(os.environ["AUDITSLIP_DB"])
bots = {
    "botA": Bot.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="botA", company_name="บริษัท A"),
    "botB": Bot.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="botB", company_name="บริษัท B"),
}
for bot in bots.values():
    bot.init_db()


def save(bot_key: str, slip_id: str, company: str, title: str, amount: float, from_account: str, to_account: str, ref: str) -> None:
    bots[bot_key].save_slip({
        "id": slip_id,
        "bot_key": bot_key,
        "company_name": company,
        "chat_id": f"{bot_key}_{'WD' if 'ถอน' in title else 'DEP'}",
        "chat_title": title,
        "message_id": int(ref[-2:]),
        "file_id": f"FILE_{slip_id}",
        "sender_name": "Uploader",
        "status": "success",
        "slip_date_display": "23/05/26",
        "slip_date_iso": "2026-05-23",
        "slip_time": "10:00",
        "transferor_name": f"ผู้ถอน {company}",
        "recipient_name": company,
        "from_bank": "SCB",
        "from_account": from_account,
        "to_bank": "KBANK",
        "to_account": to_account,
        "account_name": company,
        "amount": amount,
        "reference_no": ref,
    })


# Deposit/top-up account appears across companies, but must NOT show in cross-company account tools.
save("botA", "A_DEP_SHARED", "บริษัท A", "บริษัท A ฝาก/เติมมือ", 111.0, "DEP-SENDER-A", "DEPOSIT-SHARED-ACC", "RA01")
save("botB", "B_DEP_SHARED", "บริษัท B", "บริษัท B ฝาก", 222.0, "DEP-SENDER-B", "DEPOSIT-SHARED-ACC", "RB02")

# Withdrawal account appears across companies and should be the only cross-company account result.
save("botA", "A_WD_SHARED", "บริษัท A", "บริษัท A ถอน", 333.0, "WITHDRAW-SHARED-ACC", "WD-DEST-A", "RA03")
save("botB", "B_WD_SHARED", "บริษัท B", "บริษัท B ถอน", 444.0, "WITHDRAW-SHARED-ACC", "WD-DEST-B", "RB04")

Dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert Dash_spec and Dash_spec.loader
Dash = importlib.util.module_from_spec(Dash_spec)
sys.modules["auditslip_dashboard"] = Dash
Dash_spec.loader.exec_module(Dash)

snap_all = Dash.dashboard_snapshot(db_path, bot_key="__all__", flow_type="all", scope="2026-05-23")
cross_accounts = snap_all["account_cross_company"]
assert len(cross_accounts) == 1, cross_accounts
assert cross_accounts[0]["account"] == "WITHDRAW-SHARED-ACC", cross_accounts
assert cross_accounts[0]["total_count"] == 2 and cross_accounts[0]["total_amount"] == 777.0, cross_accounts
assert cross_accounts[0]["flow_labels"] == ["ถอน"], cross_accounts

snap_deposit_search = Dash.dashboard_snapshot(db_path, bot_key="botA", flow_type="all", scope="2026-05-23", slip_search="DEPOSITSHAREDACC")
assert snap_deposit_search["account_slip_search"]["count"] >= 1, snap_deposit_search["account_slip_search"]
dep_cross = snap_deposit_search["cross_company_account_slip_search"]
assert dep_cross.get("is_cross_company") is False, dep_cross
assert dep_cross.get("rows") == [] and dep_cross.get("count") == 0, dep_cross

snap_withdraw_search = Dash.dashboard_snapshot(db_path, bot_key="botA", flow_type="all", scope="2026-05-23", slip_search="WITHDRAWSHAREDACC")
wd_cross = snap_withdraw_search["cross_company_account_slip_search"]
assert wd_cross.get("is_cross_company") is True, wd_cross
assert wd_cross.get("company_count") == 2, wd_cross
assert {r["id"] for r in wd_cross.get("rows", [])} == {"A_WD_SHARED", "B_WD_SHARED"}, wd_cross
assert all(r["flow_type"] == "withdraw" for r in wd_cross.get("rows", [])), wd_cross

snap_deposit_filter = Dash.dashboard_snapshot(db_path, bot_key="__all__", flow_type="deposit", scope="2026-05-23", slip_search="WITHDRAWSHAREDACC")
assert snap_deposit_filter["account_cross_company"] == [], snap_deposit_filter["account_cross_company"]
assert snap_deposit_filter["cross_company_account_slip_search"].get("rows") == [], snap_deposit_filter["cross_company_account_slip_search"]

html = Dash.render_dashboard_html("test-token")
for marker in ["สลิปถอนข้ามบริษัท", "บัญชีถอนที่พบข้ามบริษัท", "เฉพาะสลิปถอน"]:
    assert marker in html, marker

print("ok: cross-company account tools ignore deposit/top-up and use withdrawal slips only")
