#!/usr/bin/env python3
"""Guard: company overview shows each company's account rows split by slip date and flow."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A,botB:BOT_TOKEN:บริษัท B"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-company-account-daily-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-company-account-daily-export-")))
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

def save(bot, slip_id: str, bot_key: str, company: str, chat_id: str, title: str, date_display: str, date_iso: str, amount: float, to_account: str, from_account: str, ref: str, duplicate: int = 0) -> None:
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
        "transferor_name": "ลูกค้า",
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

save(bot_a, "A_DEP_1", "botA", "บริษัท A", "A_DEP", "บริษัท A ฝาก/เติมมือ", "22/05/26", "2026-05-22", 100.0, "A-ACC-001", "CUST-1", "REF01")
save(bot_a, "A_DEP_2", "botA", "บริษัท A", "A_DEP", "บริษัท A ฝาก/เติมมือ", "22/05/26", "2026-05-22", 50.0, "A-ACC-001", "CUST-2", "REF02")
save(bot_a, "A_DEP_3", "botA", "บริษัท A", "A_DEP", "บริษัท A ฝาก/เติมมือ", "21/05/26", "2026-05-21", 75.0, "A-ACC-002", "CUST-3", "REF03")
save(bot_a, "A_WD_1", "botA", "บริษัท A", "A_WD", "บริษัท A ถอน", "22/05/26", "2026-05-22", 80.0, "A-WITHDRAW-DEST", "A-WD-SOURCE", "REF04")
save(bot_a, "A_DUP", "botA", "บริษัท A", "A_DEP", "บริษัท A ฝาก/เติมมือ", "22/05/26", "2026-05-22", 999.0, "A-ACC-001", "CUST-X", "REF05", duplicate=1)
save(bot_b, "B_DEP_1", "botB", "บริษัท B", "B_DEP", "บริษัท B ฝาก", "22/05/26", "2026-05-22", 200.0, "B-ACC-001", "CUST-4", "REF06")
save(bot_b, "B_DEP_CROSS_22", "botB", "บริษัท B", "B_DEP", "บริษัท B ฝาก", "22/05/26", "2026-05-22", 30.0, "A-ACC-001", "CUST-5", "REF07")
save(bot_b, "B_DEP_CROSS_21", "botB", "บริษัท B", "B_DEP", "บริษัท B ฝาก", "21/05/26", "2026-05-21", 20.0, "A-ACC-001", "CUST-6", "REF08")

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snap = Dash.dashboard_snapshot(db_path, bot_key="__all__", flow_type="all", scope="all")
rows = {(r["bot_key"], r["flow_type"], r["date_key"], r["account"]): r for r in snap["company_account_daily"]}
assert rows[("botA", "deposit", "2026-05-22", "A-ACC-001")]["count"] == 2, rows
assert rows[("botA", "deposit", "2026-05-22", "A-ACC-001")]["amount"] == 150.0, rows
assert rows[("botA", "deposit", "2026-05-21", "A-ACC-002")]["amount"] == 75.0, rows
assert rows[("botA", "withdraw", "2026-05-22", "A-WD-SOURCE")]["amount"] == 80.0, rows
assert rows[("botB", "deposit", "2026-05-22", "B-ACC-001")]["amount"] == 200.0, rows
assert rows[("botB", "deposit", "2026-05-22", "A-ACC-001")]["amount"] == 30.0, rows
assert all(r["amount"] != 999.0 for r in snap["company_account_daily"]), snap["company_account_daily"]

cross = next(r for r in snap["account_cross_company"] if r["account"] == "A-ACC-001")
assert cross["total_amount"] == 200.0 and cross["total_count"] == 4, cross
assert {c["bot_key"]: c["amount"] for c in cross["companies"]} == {"botA": 150.0, "botB": 50.0}, cross
bot_b_cross = next(c for c in cross["companies"] if c["bot_key"] == "botB")
assert {d["date_key"]: d["amount"] for d in bot_b_cross["days"]} == {"2026-05-22": 30.0, "2026-05-21": 20.0}, bot_b_cross
assert {d["date_key"]: d["amount"] for d in cross["days"]} == {"2026-05-22": 180.0, "2026-05-21": 20.0}, cross

snap_dep = Dash.dashboard_snapshot(db_path, bot_key="botA", flow_type="deposit", scope="all")
assert {r["flow_type"] for r in snap_dep["company_account_daily"]} == {"deposit"}, snap_dep["company_account_daily"]
assert {r["bot_key"] for r in snap_dep["company_account_daily"]} == {"botA"}, snap_dep["company_account_daily"]

html = Dash.render_dashboard_html("test-token")
for marker in ["companyAccountDaily", "renderCompanyAccountDaily", "รายการรายบัญชีตามวันที่", "บัญชีของบริษัท/ผู้โอน", "[กลุ่มฝาก/เติมมือ]", "[กลุ่มถอน]", "ไปอยู่บริษัทไหน / ยอดเท่าไหร่", "ยอดรายวันรวม"]:
    assert marker in html, marker

print("ok: company overview shows account rows by company and date")
