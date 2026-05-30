#!/usr/bin/env python3
"""Guard: per-account bank ledger import/preview is idempotent and matches slips by account."""
from __future__ import annotations

import email.message
import importlib.util
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-bank-ledger-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-bank-ledger-export-")))
os.environ["AUDITSLIP_BACKEND_IMPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-bank-ledger-import-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="botA", company_name="บริษัท A")
bot.init_db()


def save_slip(slip_id: str, flow: str, amount: float, hhmm: str, from_account: str, to_account: str) -> None:
    bot.save_slip({
        "id": slip_id,
        "bot_key": "botA",
        "company_name": "บริษัท A",
        "chat_id": f"CHAT_{flow}",
        "chat_title": "บริษัท A เติมมือ" if flow == "deposit" else "บริษัท A ถอน",
        "message_id": int(slip_id.rsplit('-', 1)[-1]),
        "file_id": "FILE" + slip_id,
        "sender_name": "Uploader",
        "status": "success",
        "slip_date_display": "22/05/26",
        "slip_date_iso": "2026-05-22",
        "slip_time": hhmm,
        "transferor_name": "ลูกค้า",
        "from_bank": "SCB",
        "from_account": from_account,
        "to_bank": "KBANK",
        "to_account": to_account,
        "amount": amount,
        "reference_no": slip_id,
    })


# Two slips have the same amount/time, but only one belongs to the ledger account under test.
save_slip("DEP-1", "deposit", 100.0, "11:05", "111-222-333", "999-888-777")
save_slip("DEP-2", "deposit", 100.0, "11:05", "111-222-333", "000-000-000")
save_slip("WD-3", "withdraw", 250.0, "10:15", "111-222-333", "999-888-777")

statement_xlsx = Path(os.environ["AUDITSLIP_BACKEND_IMPORT_DIR"]) / "kbank-999-statement.xlsx"
wb = Workbook()
ws = wb.active
assert ws is not None
ws.title = "Statement"
ws.append(["วันเวลา", "รายการ", "โอนออก", "รับเงินคืน", "เลขอ้างอิง"])
ws.append(["2026-05-22 11:05:00", "รับเงิน", "", 100.0, "BANK-DEP-1"])
ws.append(["2026-05-22 12:00:00", "รับเงิน", "", 777.0, "BANK-EXTRA"])
ws.append(["2026-05-22 10:15:00", "โอนออก", 250.0, "", "BANK-WD-1"])
wb.save(statement_xlsx)

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)


def count_rows(table: str) -> int:
    with Dash.connect(db_path) as conn:
        try:
            row = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
            return int(row["c"] if row else 0)
        except Exception:
            return 0


preview = Dash.preview_bank_ledger_import(
    db_path,
    statement_xlsx,
    bot_key="botA",
    company_name="บริษัท A",
    bank="KBANK",
    account_no="999-888-777",
    account_name="บริษัท A",
    flow_type="deposit",
    scope="2026-05-22",
)
assert preview["ok"] is True and preview["dry_run"] is True, preview
assert preview["account"]["bank"] == "KBANK" and preview["account"]["account_no"] == "999-888-777", preview
assert preview["incoming"]["count"] == 2 and preview["incoming"]["amount"] == 877.0, preview
assert preview["matched"]["count"] == 1 and preview["matched"]["amount"] == 100.0, preview
assert preview["ledger_extra"]["count"] == 1 and preview["ledger_extra"]["amount"] == 777.0, preview
assert preview["slip_extra"]["count"] == 0, preview
# Preview must not write ledger rows.
assert count_rows("bank_ledger_entries") == 0, preview

imported = Dash.import_bank_ledger_statement(
    db_path,
    statement_xlsx,
    bot_key="botA",
    company_name="บริษัท A",
    bank="KBANK",
    account_no="999-888-777",
    account_name="บริษัท A",
    flow_type="deposit",
    scope="2026-05-22",
    dry_run=False,
)
assert imported["ok"] is True and imported["dry_run"] is False, imported
assert imported["inserted"]["count"] == 2, imported
assert count_rows("bank_ledger_entries") == 2, imported

again = Dash.import_bank_ledger_statement(
    db_path,
    statement_xlsx,
    bot_key="botA",
    company_name="บริษัท A",
    bank="KBANK",
    account_no="999-888-777",
    account_name="บริษัท A",
    flow_type="deposit",
    scope="2026-05-22",
    dry_run=False,
)
assert again["inserted"]["count"] == 0 and again["duplicates"]["count"] == 2, again
assert count_rows("bank_ledger_entries") == 2, again

ledger = Dash.bank_ledger_snapshot(db_path, bot_key="botA", account_no="999-888-777", flow_type="deposit", scope="2026-05-22")
assert ledger["entries"]["count"] == 2 and ledger["entries"]["amount"] == 877.0, ledger
assert ledger["matched"]["count"] == 1 and ledger["unmatched_ledger"]["count"] == 1, ledger

snap = Dash.dashboard_snapshot(db_path, bot_key="botA", flow_type="deposit", scope="2026-05-22")
assert snap["bank_ledger_summary"]["entries"]["count"] == 2, snap.get("bank_ledger_summary")
assert snap["exception_summary"]["ledger_unmatched_count"] == 1, snap["exception_summary"]

html = Dash.render_dashboard_html("test-token")
for marker in [
    "section-bank-ledger",
    "statementAccountNo",
    "runBankLedgerPreview",
    "/api/ledger/preview",
    "bankLedgerSummary",
]:
    assert marker in html, marker


class _FakeHandler(Dash.DashboardHandler):
    def __init__(self, path: str, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.client_address = ("127.0.0.1", 0)
        self.request_version = "HTTP/1.1"
        self.requestline = f"POST {path} HTTP/1.1"
        self.command = "POST"
        self.path = path
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.headers = email.message.Message()
        self.headers["Authorization"] = "Bearer test-token"
        self.headers["X-Auditslip-Action"] = "dashboard"
        self.headers["Content-Type"] = "application/json"
        self.headers["Content-Length"] = str(len(body))
        self._status_code: int = 0
        self._sent_headers: List[Tuple[str, str]] = []

    def send_response(self, code: int, message: str | None = None) -> None:  # type: ignore[override]
        self._status_code = int(code)

    def send_header(self, keyword: str, value: str) -> None:  # type: ignore[override]
        self._sent_headers.append((keyword, value))

    def end_headers(self) -> None:  # type: ignore[override]
        return

    def log_message(self, fmt: str, *args: Any) -> None:  # type: ignore[override]
        return

    def json_body(self) -> Dict[str, Any]:
        return json.loads(self.wfile.getvalue().decode("utf-8") or "{}")


before_pending = count_rows("pending_actions")
before_mutations = count_rows("dashboard_mutation_log")
handler = _FakeHandler(
    "/api/ledger/preview",
    {
        "bot_key": "botA",
        "company_name": "บริษัท A",
        "bank": "KBANK",
        "account_no": "999-888-777",
        "account_name": "บริษัท A",
        "flow_type": "deposit",
        "scope": "2026-05-22",
        "statement_path": str(statement_xlsx),
    },
)
handler.do_POST()
assert handler._status_code == 200, (handler._status_code, handler.wfile.getvalue()[:400])
api_data = handler.json_body()
assert api_data["ok"] is True and api_data["dry_run"] is True, api_data
assert api_data["matched"]["count"] == 1 and api_data["ledger_extra"]["count"] == 1, api_data
assert count_rows("pending_actions") == before_pending, api_data
assert count_rows("dashboard_mutation_log") == before_mutations, api_data

print("ok: bank ledger preview/import is account-scoped, idempotent, and read-only through preview API")
