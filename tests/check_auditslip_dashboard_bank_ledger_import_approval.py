#!/usr/bin/env python3
"""Guard: bank-ledger import is gated by pending approval and imports idempotently only after execution."""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-ledger-approval-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-ledger-approval-export-")))
os.environ["AUDITSLIP_BACKEND_IMPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-ledger-approval-import-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="botA", company_name="บริษัท A")
bot.init_db()

bot.save_slip({
    "id": "LEDGER-APPROVAL-SLIP-1",
    "bot_key": "botA",
    "company_name": "บริษัท A",
    "chat_id": "CHAT_DEPOSIT",
    "chat_title": "บริษัท A เติมมือ",
    "message_id": 1,
    "file_id": "FILE1",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "11:05",
    "transferor_name": "ลูกค้า",
    "from_bank": "SCB",
    "from_account": "111-222-333",
    "to_bank": "KBANK",
    "to_account": "999-888-777",
    "amount": 100.0,
    "reference_no": "LEDGER-APPROVAL-SLIP-1",
})

statement_xlsx = Path(os.environ["AUDITSLIP_BACKEND_IMPORT_DIR"]) / "kbank-approval-ledger.xlsx"
wb = Workbook()
ws = wb.active
assert ws is not None
ws.title = "Statement"
ws.append(["วันเวลา", "รายการ", "โอนออก", "รับเงินคืน", "เลขอ้างอิง"])
ws.append(["2026-05-22 11:05:00", "รับเงิน", "", 100.0, "BANK-APPROVAL-1"])
ws.append(["2026-05-22 12:00:00", "รับเงิน", "", 777.0, "BANK-APPROVAL-EXTRA"])
wb.save(statement_xlsx)

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)


def table_count(table: str, where: str = "1=1") -> int:
    with sqlite3.connect(db_path) as conn:
        try:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0])
        except sqlite3.OperationalError:
            return 0

payload = {
    "bot_key": "botA",
    "company_name": "บริษัท A",
    "bank": "KBANK",
    "account_no": "999-888-777",
    "account_name": "บริษัท A",
    "flow_type": "deposit",
    "scope": "2026-05-22",
    "statement_path": str(statement_xlsx),
}

preview = Dash.preview_bank_ledger_import(db_path, statement_xlsx, **{k: v for k, v in payload.items() if k != "statement_path"})
assert preview["ok"] is True and preview["dry_run"] is True, preview
assert preview["incoming"]["count"] == 2 and preview["matched"]["count"] == 1, preview
assert table_count("bank_ledger_entries") == 0, "preview must not import ledger rows"

pending_id = Dash.create_pending_action(
    db_path,
    action="ledger.import",
    payload=payload,
    requested_by="requester-a",
    request_id="ledger-import-test",
)
blocked = Dash.execute_pending_action(db_path, pending_id, "requester-a")
assert blocked["ok"] is False and blocked["status_code"] == 409, blocked
assert table_count("bank_ledger_entries") == 0, "unapproved import must not insert ledger rows"

self_approval = Dash.approve_pending_action(db_path, pending_id, "requester-a")
assert self_approval["ok"] is False and self_approval["status"] == 403, self_approval
approval = Dash.approve_pending_action(db_path, pending_id, "approver-b")
assert approval["ok"] is True, approval
executed = Dash.execute_pending_action(db_path, pending_id, "approver-b")
assert executed["ok"] is True and executed["status"] == "executed", executed
assert executed["action"] == "ledger.import", executed
assert executed["inserted"]["count"] == 2, executed
assert table_count("bank_ledger_entries") == 2, executed

again = Dash.import_bank_ledger_statement(db_path, statement_xlsx, dry_run=False, **{k: v for k, v in payload.items() if k != "statement_path"})
assert again["inserted"]["count"] == 0 and again["duplicates"]["count"] == 2, again

pending = Dash.load_pending_action(db_path, pending_id)
assert pending["status"] == "executed", pending
assert table_count("dashboard_mutation_log", "action='ledger_import'") == 1
assert table_count("dashboard_mutation_log", "action='ledger_import.request'") == 0  # direct helper path only logs execution

html = Dash.render_dashboard_html("test-token")
for marker in ["/api/ledger/import", "requestBankLedgerImport", "ขอ Import หลัง approval", "ledger.import"]:
    assert marker in html, f"missing rendered marker: {marker}"

print("ok: bank ledger import waits for approval, executes once, and records mutation")
