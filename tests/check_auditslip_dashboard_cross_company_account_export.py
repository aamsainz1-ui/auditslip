#!/usr/bin/env python3
"""Guard: cross-company account slip search can be exported as one Excel workbook."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A,botB:BOT_TOKEN:บริษัท B,botC:BOT_TOKEN:บริษัท C"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-cross-account-export-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-cross-account-export-out-")))
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
        "fee": 0.0,
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

xlsx = Dash.export_cross_company_account_slips_excel(
    db_path,
    flow_type="deposit",
    scope="2026-05-22",
    search="SHAREDACC789",
)
assert xlsx.suffix == ".xlsx" and xlsx.exists(), xlsx
wb = load_workbook(xlsx, data_only=True)
assert {"SummaryByCompany", "CrossCompanyAccountSlips"}.issubset(set(wb.sheetnames)), wb.sheetnames

summary_rows = list(wb["SummaryByCompany"].iter_rows(values_only=True))
summary_headers = list(summary_rows[0])
summary = [dict(zip(summary_headers, row)) for row in summary_rows[1:]]
assert {str(row["company_name"] or "") for row in summary} == {"บริษัท A", "บริษัท B"}, summary
assert sum(int(float(str(row["count"] or 0))) for row in summary) == 2, summary
assert sum(float(str(row["amount"] or 0)) for row in summary) == 350.0, summary

slip_rows = list(wb["CrossCompanyAccountSlips"].iter_rows(values_only=True))
headers = list(slip_rows[0])
records = [dict(zip(headers, row)) for row in slip_rows[1:]]
refs = [row["reference_no"] for row in records]
assert refs == ["RB02", "RA01"], records
assert "RB04" not in refs and "RA05" not in refs and "RC03" not in refs, records
assert "matched_label" in headers and "slip_image_url" in headers, headers
assert "id" not in headers and "bot_key" not in headers and "file_id" not in headers, headers
assert all(str(row["slip_image_url"]).startswith("/api/slip-image?id=") for row in records), records

html = Dash.render_dashboard_html("test-token")
for marker in [
    "buildCrossCompanyAccountExcelUrl",
    "cross_account_search",
    "ส่งออก Excel ข้ามบริษัท",
    "target=\"exportDownloadFrame\"",
]:
    assert marker in html, marker

print("ok: cross-company account slip search exports one Excel workbook")
