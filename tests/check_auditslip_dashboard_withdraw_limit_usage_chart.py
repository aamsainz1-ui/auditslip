#!/usr/bin/env python3
"""Guard: dashboard exposes a company-level withdrawal usage vs total limit chart."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A,botB:BOT_TOKEN:บริษัท B"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-withdraw-limit-chart-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-withdraw-limit-chart-export-")))
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


def save(bot, slip_id: str, bot_key: str, company: str, chat_id: str, title: str, amount: float, bank: str, account: str, ref: str, duplicate: int = 0) -> None:
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
        "slip_date_display": "23/05/26",
        "slip_date_iso": "2026-05-23",
        "slip_time": "10:00",
        "transferor_name": "บัญชีถอน",
        "recipient_name": company,
        "issuer_bank": bank,
        "from_bank": bank,
        "from_account": account,
        "to_bank": "KBANK",
        "to_account": f"TO-{company}",
        "account_name": company,
        "amount": amount,
        "reference_no": ref,
        "is_duplicate": duplicate,
    })


save(bot_a, "A_KTB", "botA", "บริษัท A", "A_WD", "บริษัท A ถอน", 30_000.0, "KRUNGTHAI", "A-KTB-001", "RA01")
save(bot_a, "A_SCB", "botA", "บริษัท A", "A_WD", "บริษัท A ถอน", 120_000.0, "SCB", "A-SCB-001", "RA02")
save(bot_a, "A_DUP", "botA", "บริษัท A", "A_WD", "บริษัท A ถอน", 999_999.0, "SCB", "A-SCB-001", "RA03", duplicate=1)
save(bot_b, "B_KTB", "botB", "บริษัท B", "B_WD", "บริษัท B ถอน", 60_000.0, "KRUNGTHAI", "B-KTB-001", "RB01")

# Deposit/top-up must not inflate withdrawal usage or withdrawal capacity.
save(bot_b, "B_DEP", "botB", "บริษัท B", "B_DEP", "บริษัท B ฝาก/เติมมือ", 1_000_000.0, "SCB", "B-CUSTOMER", "RB02")

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snap = Dash.dashboard_snapshot(db_path, bot_key="__all__", flow_type="all", scope="2026-05-23")
rows = {r["bot_key"]: r for r in snap["withdraw_limit_usage"]}
assert set(rows) == {"botA", "botB"}, rows

company_a = rows["botA"]
assert company_a["company_name"] == "บริษัท A", company_a
assert company_a["withdraw_amount"] == 150_000.0, company_a
assert company_a["withdraw_count"] == 2, company_a
assert company_a["limit_amount"] == 250_000.0, company_a
assert company_a["remaining_amount"] == 100_000.0, company_a
assert round(company_a["usage_percent"], 2) == 60.0, company_a
assert company_a["account_count"] == 2 and company_a["account_day_count"] == 2, company_a
assert company_a["over_limit"] is False, company_a

company_b = rows["botB"]
assert company_b["withdraw_amount"] == 60_000.0, company_b
assert company_b["limit_amount"] == 50_000.0, company_b
assert company_b["remaining_amount"] == -10_000.0, company_b
assert company_b["over_limit_amount"] == 10_000.0, company_b
assert round(company_b["usage_percent"], 2) == 120.0, company_b
assert company_b["over_limit"] is True, company_b

totals = snap["totals"]
assert totals["withdraw_limit_capacity_amount"] == 300_000.0, totals
assert totals["withdraw_limit_remaining_amount"] == 90_000.0, totals
assert totals["withdraw_limit_over_amount"] == 10_000.0, totals
assert round(totals["withdraw_limit_usage_percent"], 2) == 70.0, totals

html = Dash.render_dashboard_html("test-token")
for marker in [
    "withdrawLimitUsageChart",
    "renderWithdrawLimitUsageChart",
    "ยอดถอนรวม / วงเงินรวมทุกบัญชี",
    "withdraw_limit_usage",
    "withdraw_limit_capacity_amount",
]:
    assert marker in html, marker

print("ok: dashboard exposes withdrawal usage vs total limit chart")
