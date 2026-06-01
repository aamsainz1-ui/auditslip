#!/usr/bin/env python3
"""Guard: cross-company account UI exposes sender/uploader context and a dedicated section."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A,botB:BOT_TOKEN:บริษัท B,botC:BOT_TOKEN:บริษัท C"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-cross-sender-display-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-cross-sender-display-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bots = {
    "botA": bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="botA", company_name="บริษัท A"),
    "botB": bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="botB", company_name="บริษัท B"),
    "botC": bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="botC", company_name="บริษัท C"),
}
for bot in bots.values():
    bot.init_db()


def save(bot_key: str, slip_id: str, company: str, amount: float, from_account: str, ref: str, sender_name: str, username: str) -> None:
    bots[bot_key].save_slip({
        "id": slip_id,
        "bot_key": bot_key,
        "company_name": company,
        "chat_id": f"{bot_key}_WD",
        "chat_title": f"{company} ถอน",
        "message_id": int(ref[-2:]),
        "file_id": f"FILE_{slip_id}",
        "sender_name": sender_name,
        "username": username,
        "status": "success",
        "slip_date_display": "24/05/26",
        "slip_date_iso": "2026-05-24",
        "slip_time": "10:00",
        "transferor_name": f"ผู้ถอน {company}",
        "recipient_name": company,
        "from_bank": "SCB",
        "from_account": from_account,
        "to_bank": "KBANK",
        "to_account": f"DEST-{bot_key}",
        "account_name": company,
        "amount": amount,
        "reference_no": ref,
    })


save("botA", "A_SHARED_1", "บริษัท A", 100.0, "SHARED-ACC-456", "RA01", "Alice Sender", "alice_a")
save("botA", "A_SHARED_2", "บริษัท A", 50.0, "SHARED-ACC-456", "RA02", "Alice Sender", "alice_a")
save("botB", "B_SHARED_1", "บริษัท B", 200.0, "SHARED-ACC-456", "RB03", "Bob Sender", "bob_b")
save("botC", "C_OTHER", "บริษัท C", 999.0, "OTHER-ACC", "RC04", "Charlie Sender", "charlie_c")

spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert spec and spec.loader
Dash = importlib.util.module_from_spec(spec)
sys.modules["auditslip_dashboard"] = Dash
spec.loader.exec_module(Dash)

snap = Dash.dashboard_snapshot(db_path, bot_key="__all__", flow_type="withdraw", scope="2026-05-24")
cross_accounts = snap["account_cross_company"]
assert len(cross_accounts) == 1, cross_accounts
account = cross_accounts[0]
assert account["account"] == "SHARED-ACC-456", account
companies = {c["bot_key"]: c for c in account["companies"]}
assert set(companies) == {"botA", "botB"}, companies
assert companies["botA"]["senders"] == [
    {"sender_name": "Alice Sender", "username": "alice_a", "display_name": "Alice Sender (@alice_a)", "count": 2, "amount": 150.0}
], companies["botA"]
assert companies["botB"]["senders"] == [
    {"sender_name": "Bob Sender", "username": "bob_b", "display_name": "Bob Sender (@bob_b)", "count": 1, "amount": 200.0}
], companies["botB"]

search = Dash.dashboard_snapshot(db_path, bot_key="__all__", flow_type="withdraw", scope="2026-05-24", slip_search="SHAREDACC456", account_search_mode="cross")
cross_search = search["cross_company_account_slip_search"]
assert cross_search["is_cross_company"] is True, cross_search
assert {r["sender_display"] for r in cross_search["rows"]} == {"Alice Sender (@alice_a)", "Bob Sender (@bob_b)"}, cross_search["rows"]
assert {c["display_name"] for company in cross_search["companies"] for c in company["senders"]} == {"Alice Sender (@alice_a)", "Bob Sender (@bob_b)"}, cross_search["companies"]

html = Dash.render_dashboard_html("test-token")
for marker in [
    "section-cross-company-accounts",
    "ยอดข้ามบริษัท",
    "บริษัทที่มีสลิปของบัญชีนี้",
    "ผู้ส่งรูป",
    "sender_display",
    "renderAccountCrossCompany",
    "renderCrossCompanyAccountSlipSearch",
]:
    assert marker in html, marker

print("ok: cross-company account section shows companies and Telegram senders")
