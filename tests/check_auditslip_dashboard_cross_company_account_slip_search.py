#!/usr/bin/env python3
"""Guard: dashboard can search one account's individual slips across companies."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A,botB:BOT_TOKEN:บริษัท B,botC:BOT_TOKEN:บริษัท C"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-cross-account-slip-search-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-cross-account-slip-search-export-")))
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


def save(bot_key: str, slip_id: str, company: str, chat_id: str, title: str, amount: float, to_account: str, ref: str, duplicate: int = 0, date_iso: str = "2026-05-22") -> None:
    bots[bot_key].save_slip({
        "id": slip_id,
        "bot_key": bot_key,
        "company_name": company,
        "chat_id": chat_id,
        "chat_title": title,
        "message_id": int(ref[-2:]) if ref[-2:].isdigit() else 1,
        "file_id": f"FILE_{slip_id}",
        "sender_name": "Uploader",
        "status": "success",
        "slip_date_display": "22/05/26" if date_iso == "2026-05-22" else "21/05/26",
        "slip_date_iso": date_iso,
        "slip_time": "10:00",
        "transferor_name": f"ลูกค้า {company}",
        "recipient_name": company,
        "from_bank": "SCB",
        "from_account": f"FROM-{bot_key}",
        "to_bank": "KBANK",
        "to_account": to_account,
        "account_name": company,
        "amount": amount,
        "reference_no": ref,
        "is_duplicate": duplicate,
    })


save("botA", "A_SHARED", "บริษัท A", "A_DEP", "บริษัท A ฝาก", 100.0, "SHARED-ACC-789", "RA01")
save("botB", "B_SHARED", "บริษัท B", "B_DEP", "บริษัท B ฝาก/เติมมือ", 250.0, "SHARED-ACC-789", "RB02")
save("botC", "C_OTHER", "บริษัท C", "C_DEP", "บริษัท C ฝาก", 999.0, "OTHER-ACC", "RC03")
save("botB", "B_DUP", "บริษัท B", "B_DEP", "บริษัท B ฝาก/เติมมือ", 888.0, "SHARED-ACC-789", "RB04", duplicate=1)
save("botA", "A_OLD", "บริษัท A", "A_DEP", "บริษัท A ฝาก", 777.0, "SHARED-ACC-789", "RA05", date_iso="2026-05-21")

spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert spec and spec.loader
Dash = importlib.util.module_from_spec(spec)
sys.modules["auditslip_dashboard"] = Dash
spec.loader.exec_module(Dash)

# Selected company stays botA, but the new cross-company search must search every company.
snap = Dash.dashboard_snapshot(db_path, bot_key="botA", flow_type="deposit", scope="2026-05-22", slip_search="SHAREDACC789")
scoped = snap["account_slip_search"]
cross = snap["cross_company_account_slip_search"]

assert scoped["count"] == 1 and scoped["amount"] == 100.0, scoped
assert [r["id"] for r in scoped["rows"]] == ["A_SHARED"], scoped["rows"]
assert cross["query"] == "SHAREDACC789", cross
assert cross["count"] == 2, cross
assert cross["amount"] == 350.0, cross
assert cross["company_count"] == 2, cross
assert {c["bot_key"] for c in cross["companies"]} == {"botA", "botB"}, cross
assert {r["id"] for r in cross["rows"]} == {"A_SHARED", "B_SHARED"}, cross["rows"]
assert all(r["image_url"].startswith("/api/slip-image?id=") for r in cross["rows"]), cross["rows"]
assert all(r["status"] == "success" and not int(r.get("is_duplicate") or 0) for r in cross["rows"]), cross["rows"]
assert all(r["date_key"] == "2026-05-22" for r in cross["rows"]), cross["rows"]

with Dash.connect(db_path) as conn:
    limited = Dash.cross_company_account_slip_search_rows(conn, scope="2026-05-22", flow_type="deposit", search="SHAREDACC789", limit=1)
assert len(limited["rows"]) == 1, limited
assert limited["count"] == 2 and limited["company_count"] == 2, limited
assert {c["bot_key"] for c in limited["companies"]} == {"botA", "botB"}, limited

snap_empty = Dash.dashboard_snapshot(db_path, bot_key="botA", flow_type="deposit", scope="2026-05-22", slip_search="")
assert snap_empty["cross_company_account_slip_search"]["rows"] == [], snap_empty["cross_company_account_slip_search"]

html = Dash.render_dashboard_html("test-token")
for marker in [
    "crossCompanyAccountSlipSearch",
    "renderCrossCompanyAccountSlipSearch",
    "ดูสลิปข้ามบริษัท",
    "data-cross-account-search",
    "ค้นหาสลิปบัญชีข้ามบริษัท",
]:
    assert marker in html, marker

print("ok: dashboard searches individual account slips across companies")
