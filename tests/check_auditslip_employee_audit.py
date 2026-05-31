#!/usr/bin/env python3
"""Guard: employee audit covers slip-ledger reconcile, daily employee totals, and cross-bot duplicates."""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A,botB:BOT_TOKEN:บริษัท B"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-employee-audit-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-employee-audit-export-")))
os.environ["AUDITSLIP_BACKEND_IMPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-employee-audit-import-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

ledger_spec = importlib.util.spec_from_file_location("auditslip_bank_ledger", ROOT / "auditslip_bank_ledger.py")
assert ledger_spec and ledger_spec.loader
ledger_mod = importlib.util.module_from_spec(ledger_spec)
sys.modules["auditslip_bank_ledger"] = ledger_mod
ledger_spec.loader.exec_module(ledger_mod)

audit_spec = importlib.util.spec_from_file_location("auditslip_audit_employee", ROOT / "auditslip_audit_employee.py")
assert audit_spec and audit_spec.loader
Audit = importlib.util.module_from_spec(audit_spec)
sys.modules["auditslip_audit_employee"] = Audit
audit_spec.loader.exec_module(Audit)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot_a = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="botA", company_name="บริษัท A")
bot_b = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="botB", company_name="บริษัท B")
bot_a.init_db()


def save(bot: object, slip_id: str, bot_key: str, company: str, amount: float, ref: str, account: str) -> None:
    bot.save_slip({
        "id": slip_id,
        "bot_key": bot_key,
        "company_name": company,
        "chat_id": f"{bot_key}_DEP",
        "chat_title": f"{company} ฝาก",
        "message_id": int(slip_id.rsplit("-", 1)[-1]),
        "file_id": "FILE" + slip_id,
        "sender_name": "Uploader",
        "status": "success",
        "slip_date_display": "22/05/26",
        "slip_date_iso": "2026-05-22",
        "slip_time": "11:05",
        "transferor_name": "Alice",
        "from_bank": "SCB",
        "from_account": "111-222-333",
        "to_bank": "KBANK",
        "to_account": account,
        "amount": amount,
        "reference_no": ref,
    })


save(bot_a, "A-1", "botA", "บริษัท A", 100.0, "REF-100", "999-888-777")
save(bot_a, "A-2", "botA", "บริษัท A", 55.0, "REF-055", "000-000-000")
save(bot_b, "B-3", "botB", "บริษัท B", 100.0, "REF-100", "999-888-777")

with sqlite3.connect(db_path) as conn:
    ledger_mod.ensure_bank_ledger_tables(conn)
    conn.executemany(
        """
        INSERT INTO bank_ledger_entries(
          entry_id, bot_key, account_key, company_name, bank, account_no, account_name,
          source_name, source_hash, row_no, date, date_key, time, flow_type, flow_label,
          description, amount, reference, sender, receiver, imported_at, raw_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        [
            ("E-1", "botA", "kbank|999888777", "บริษัท A", "KBANK", "999-888-777", "บริษัท A", "test.csv", "H1", 1, "2026-05-22", "2026-05-22", "11:05", "deposit", "ฝาก", "รับเงิน", 100.0, "REF-100", "Alice", "บริษัท A", 1, "{}"),
            ("E-2", "botA", "kbank|999888777", "บริษัท A", "KBANK", "999-888-777", "บริษัท A", "test.csv", "H2", 2, "2026-05-22", "2026-05-22", "12:00", "deposit", "ฝาก", "รับเงินเกิน", 77.0, "EXTRA-77", "Other", "บริษัท A", 1, "{}"),
        ],
    )

reconcile = Audit.reconcile_slips_ledger(db_path, bot_key="botA", account_key="999-888-777", scope="2026-05-22", flow_type="deposit")
assert reconcile["ok"] is True and reconcile["has_ledger"] is True, reconcile
assert reconcile["summary"]["matched_count"] == 1, reconcile
assert reconcile["summary"]["ledger_only_count"] == 1, reconcile
assert reconcile["summary"]["slip_only_count"] == 0, reconcile

variance = Audit.employee_daily_variance(db_path, bot_key="botA", scope="2026-05-22", flow_type="deposit", threshold=10)
assert variance["ok"] is True and variance["has_ledger"] is True, variance
assert variance["employee_count"] >= 1 and variance["flagged_count"] >= 1, variance

cross = Audit.cross_bot_duplicates(db_path, scope="2026-05-22")
assert cross["ok"] is True and cross["group_count"] == 1, cross
assert cross["groups"][0]["source_count"] == 2, cross

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

html = Dash.render_dashboard_html("test-token")
for marker in ["section-employee-audit", "runEmployeeAudit", "/api/audit/reconcile", "/api/audit/daily-variance", "/api/audit/cross-dup"]:
    assert marker in html, marker

print("ok: employee audit 1-2-3 covers reconcile, daily variance, and cross-bot duplicates")
