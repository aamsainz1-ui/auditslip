#!/usr/bin/env python3
"""Guard: dashboard can compare backend amount/time, slip amount/time, and bank statement rows."""
from __future__ import annotations

import csv
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A,botB:BOT_TOKEN:บริษัท B"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-statement-reconcile-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-statement-reconcile-export-")))
os.environ["AUDITSLIP_BACKEND_IMPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-statement-reconcile-import-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="botA", company_name="บริษัท A")
bot.init_db()


def save_slip(idx: int, flow: str, amount: float, hhmm: str, ref: str) -> None:
    bot.save_slip({
        "id": f"SLIP-{flow}-{idx}",
        "bot_key": "botA",
        "company_name": "บริษัท A",
        "chat_id": f"CHAT_{flow}",
        "chat_title": "บริษัท A เติมมือ" if flow == "deposit" else "บริษัท A ถอน",
        "message_id": idx,
        "file_id": f"FILE{idx}",
        "sender_name": "Uploader",
        "status": "success",
        "slip_date_display": "22/05/26",
        "slip_date_iso": "2026-05-22",
        "slip_time": hhmm,
        "transferor_name": "ลูกค้า",
        "from_bank": "SCB",
        "to_bank": "KBANK",
        "amount": amount,
        "reference_no": ref,
    })


save_slip(1, "withdraw", 250.0, "10:15", "WD250")
save_slip(2, "deposit", 100.0, "11:05", "DEP100")


def make_backend_xlsx(filename: str, amount: float, hhmm: str) -> Path:
    xlsx = Path(os.environ["AUDITSLIP_BACKEND_IMPORT_DIR"]) / filename
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Backend"
    # Backend often has only amount/time, no bank/name/ref evidence.
    ws.append(["เวลา", "ยอดเงิน"])
    ws.append([f"2026-05-22 {hhmm}:00", amount])
    wb.save(xlsx)
    return xlsx


statement_xlsx = Path(os.environ["AUDITSLIP_BACKEND_IMPORT_DIR"]) / "statement.xlsx"
wb = Workbook()
ws = wb.active
assert ws is not None
ws.title = "Statement"
ws.append(["วันเวลา", "รายการ", "โอนออก", "รับเงินคืน"])
ws.append(["2026-05-22 10:15:00", "โอนออก", 250.0, ""])
ws.append(["2026-05-22 11:05:00", "รับเงินคืน", "", 100.0])
ws.append(["2026-05-22 12:00:00", "โอนออก", 999.0, ""])
wb.save(statement_xlsx)

statement_csv = Path(os.environ["AUDITSLIP_BACKEND_IMPORT_DIR"]) / "truewallet-statement.csv"
with statement_csv.open("w", encoding="utf-8-sig", newline="") as out:
    writer = csv.writer(out)
    # True Wallet Dashboard CSV export format from port 3050.
    writer.writerow(["วันที่", "เบอร์ผู้โอน", "เบอร์ผู้รับ", "จำนวน (บาท)", "หมายเหตุ", "Transaction ID"])
    writer.writerow(["2026-05-22 11:05:00", "0811111111", "0899999999", "100.00", "", "TW-DEP100"])
    writer.writerow(["2026-05-22 12:00:00", "0822222222", "0899999999", "777.00", "", "TW-EXTRA"])


dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

statement_rows = Dash.parse_statement_excel(statement_xlsx)
flows = {(r["amount"], r["time"]): r["flow_type"] for r in statement_rows}
assert flows[(250.0, "10:15")] == "withdraw", statement_rows
assert flows[(100.0, "11:05")] == "deposit", statement_rows

csv_rows = Dash.parse_statement_file(statement_csv)
csv_flows = {(r["amount"], r["time"]): r["flow_type"] for r in csv_rows}
assert csv_flows[(100.0, "11:05")] == "deposit", csv_rows
assert csv_flows[(777.0, "12:00")] == "deposit", csv_rows
assert Dash.safe_statement_file_path(statement_csv.name) == statement_csv.resolve()

wd = Dash.reconcile_backend_slips_statement(
    db_path,
    make_backend_xlsx("backend-withdraw.xlsx", 250.0, "10:15"),
    statement_xlsx,
    bot_key="botA",
    flow_type="withdraw",
    scope="2026-05-22",
)
assert wd["ok"] is True, wd
assert wd["backend"]["count"] == 1 and wd["backend"]["amount"] == 250.0, wd
assert wd["slips"]["count"] == 1 and wd["slips"]["amount"] == 250.0, wd
assert wd["statement"]["count"] == 2 and wd["statement"]["amount"] == 1249.0, wd
assert wd["matched"]["count"] == 1 and wd["matched"]["amount"] == 250.0, wd
assert wd["statement_extra"]["count"] == 1 and wd["statement_extra"]["amount"] == 999.0, wd
assert wd["backend_missing_slip"]["count"] == 0 and wd["backend_missing_statement"]["count"] == 0, wd

dep = Dash.reconcile_backend_slips_statement(
    db_path,
    make_backend_xlsx("backend-deposit.xlsx", 100.0, "11:05"),
    statement_xlsx,
    bot_key="botA",
    flow_type="deposit",
    scope="2026-05-22",
)
assert dep["statement"]["count"] == 1 and dep["statement"]["amount"] == 100.0, dep
assert dep["matched"]["count"] == 1 and dep["matched"]["amount"] == 100.0, dep
assert dep["statement_extra"]["count"] == 0, dep

csv_dep = Dash.reconcile_backend_slips_statement(
    db_path,
    make_backend_xlsx("backend-deposit-csv.xlsx", 100.0, "11:05"),
    statement_csv,
    bot_key="botA",
    flow_type="deposit",
    scope="2026-05-22",
)
assert csv_dep["statement"]["count"] == 2 and csv_dep["statement"]["amount"] == 877.0, csv_dep
assert csv_dep["matched"]["count"] == 1 and csv_dep["matched"]["amount"] == 100.0, csv_dep
assert csv_dep["statement_extra"]["count"] == 1 and csv_dep["statement_extra"]["amount"] == 777.0, csv_dep

html = Dash.render_dashboard_html("test-token")
for marker in [
    "เทียบ 3 ฝั่ง",
    "รายการเดินบัญชี",
    "statementExcelFile",
    ".xlsx,.xlsm,.csv",
    "statement_path",
    "runStatementReconcile",
    "/api/reconcile/statement",
    "previousReconcileBot",
]:
    assert marker in html, marker

print("ok: statement reconciliation compares backend, slips, and bank statement by amount/time")
