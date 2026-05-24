#!/usr/bin/env python3
"""Guard: deposit/manual top-up account rows merge compatible masked account formats."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot3:BOT_TOKEN:บริษัท 3"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-deposit-mask-group-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-deposit-mask-group-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="bot3", company_name="บริษัท 3")
bot.init_db()

base = {
    "bot_key": "bot3",
    "company_name": "บริษัท 3",
    "chat_id": "CHAT_DEP_MANUAL",
    "chat_title": "333 สลิป (เติมมือ)",
    "sender_name": "Uploader",
    "username": "operator",
    "status": "success",
    "slip_date_display": "24/05/26",
    "slip_date_iso": "2026-05-24",
    "issuer_bank": "SCB",
    "from_bank": "KBANK",
    "from_account": "ลูกค้าต้นทาง",
    "to_bank": "SCB",
    "recipient_name": "บริษัท 3",
    "confidence": 0.99,
}

# Same destination account, two slip/OCR mask formats.  Known digits do not
# conflict after stripping separators: 8XX2XXX315 + XXXXXX9315 => compatible.
bot.save_slip({**base, "id": "DEP-MASK-A", "message_id": 101, "file_id": "FILE_A", "slip_time": "10:01", "transferor_name": "ลูกค้า A", "to_account": "8XX-2-XXX31-5", "amount": 100.0, "reference_no": "REF-A"})
bot.save_slip({**base, "id": "DEP-MASK-B", "message_id": 102, "file_id": "FILE_B", "slip_time": "10:02", "transferor_name": "ลูกค้า B", "to_account": "XXX-X-XX931-5", "amount": 200.0, "reference_no": "REF-B"})

# Looks similar by suffix but conflicts on known digits, so it must stay a
# separate account row and must not be pulled into the drill-down.
bot.save_slip({**base, "id": "DEP-MASK-CONFLICT", "message_id": 103, "file_id": "FILE_C", "slip_time": "10:03", "transferor_name": "ลูกค้า C", "to_account": "7XX-2-XX831-5", "amount": 999.0, "reference_no": "REF-C"})

# A withdrawal row with the same visible account must not affect the deposit
# destination-account grouping.
bot.save_slip({**base, "id": "WD-SAME-TEXT", "chat_id": "CHAT_WD", "chat_title": "333 สลิปถอน", "message_id": 201, "file_id": "FILE_WD", "slip_time": "11:01", "transferor_name": "บัญชีถอน", "from_bank": "SCB", "from_account": "8XX-2-XXX31-5", "to_account": "ปลายทางถอน", "amount": 50.0, "reference_no": "REF-WD"})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snap = Dash.dashboard_snapshot(db_path, bot_key="bot3", flow_type="deposit", scope="2026-05-24")
dep_rows = [r for r in snap["company_account_daily"] if r["flow_type"] == "deposit"]
assert len(dep_rows) == 2, dep_rows

grouped = next((r for r in dep_rows if int(r["count"]) == 2), None)
assert grouped is not None, dep_rows
assert grouped["amount"] == 300.0, grouped
assert grouped["bank"] == "SCB", grouped
assert grouped["account_role"] == "บัญชีรับเงิน/ปลายทาง", grouped
assert grouped["account"] == "8XX-2-XXX31-5", grouped  # keep the most informative existing display, do not synthesize a new account number
assert sorted(grouped.get("account_aliases") or []) == ["8XX-2-XXX31-5", "XXX-X-XX931-5"], grouped

conflict = next((r for r in dep_rows if r["account"] == "7XX-2-XX831-5"), None)
assert conflict is not None and conflict["count"] == 1 and conflict["amount"] == 999.0, dep_rows

# The row button uses the displayed account as the query; mask-compatible search
# must find both same-account slips and exclude the known-digit conflict.
with Dash.connect(db_path) as conn:
    where, params, _ = Dash.global_scope_where("2026-05-24", success_only=True, bot_key="bot3")
    where, params = Dash.apply_flow_sql(where, params, "deposit")
    result = Dash.account_slip_search_rows(conn, where, params, grouped["account"])
assert result["count"] == 2, result
assert result["amount"] == 300.0, result
assert {row["id"] for row in result["rows"]} == {"DEP-MASK-A", "DEP-MASK-B"}, result["rows"]

print("ok: deposit masked account variants merge safely and drill down together")
