#!/usr/bin/env python3
"""Guard: one withdrawal account used by multiple companies has one real daily limit."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A,botB:BOT_TOKEN:บริษัท B"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-shared-limit-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-shared-limit-export-")))
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
}
for bot in bots.values():
    bot.init_db()


def save(bot_key: str, slip_id: str, company: str, amount: float, ref: str, account: str = "SHARED-LIMIT-ACC") -> None:
    bots[bot_key].save_slip({
        "id": slip_id,
        "bot_key": bot_key,
        "company_name": company,
        "chat_id": f"{bot_key}_WD",
        "chat_title": f"{company} ถอน",
        "message_id": int(ref[-2:]),
        "file_id": f"FILE_{slip_id}",
        "sender_name": f"Sender {company[-1]}",
        "status": "success",
        "slip_date_display": "25/05/26",
        "slip_date_iso": "2026-05-25",
        "slip_time": "10:00",
        "transferor_name": "SHARED OWNER",
        "recipient_name": company,
        "from_bank": "SCB",
        "from_account": account,
        "to_bank": "KBANK",
        "to_account": f"DEST-{bot_key}",
        "amount": amount,
        "reference_no": ref,
    })


# Add enough higher-amount accounts to push the shared account beyond the 120-row display cap.
# The real shared-limit calculation must use the full account-day rowset, not the capped table rows.
FILLER_COUNT = 130
FILLER_AMOUNT = 150_000.0
for i in range(FILLER_COUNT):
    save("botA", f"A_FILLER_{i:03d}", "บริษัท A", FILLER_AMOUNT, f"RF{i:02d}", account=f"FILLER-ACC-{i:03d}")

# Same physical SCB withdrawal account used in two companies on the same day.
# SCB default limit is 200,000. The real account usage is 120,000 + 90,000 = 210,000,
# so it is over by 10,000 even though each company row alone looks below 200,000.
save("botA", "A_SHARED_LIMIT", "บริษัท A", 120_000.0, "RA01")
save("botB", "B_SHARED_LIMIT", "บริษัท B", 90_000.0, "RB02")

spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert spec and spec.loader
Dash = importlib.util.module_from_spec(spec)
sys.modules["auditslip_dashboard"] = Dash
spec.loader.exec_module(Dash)

snap = Dash.dashboard_snapshot(db_path, bot_key="__all__", flow_type="all", scope="2026-05-25")
company_rows = [r for r in snap["by_account_day"] if r["account"] == "SHARED-LIMIT-ACC"]
assert len(company_rows) < 2, company_rows  # display rows are intentionally capped; calculation below must still see both companies.
assert len(snap["by_account_day"]) == 120, len(snap["by_account_day"])

shared = snap["shared_withdraw_limit_usage"]
assert len(shared) == 1, shared
row = shared[0]
assert row["account"] == "SHARED-LIMIT-ACC", row
assert row["company_count"] == 2, row
assert row["amount"] == 210_000.0, row
assert row["daily_limit"] == 200_000.0, row
assert row["remaining_amount"] == -10_000.0, row
assert row["over_limit"] is True, row
assert row["duplicate_capacity_amount"] == 400_000.0, row
assert {c["bot_key"] for c in row["companies"]} == {"botA", "botB"}, row

# Overall capacity should not double-count the same physical account limit.
totals = snap["totals"]
expected_capacity = (FILLER_COUNT + 1) * 200_000.0
expected_withdraw = (FILLER_COUNT * FILLER_AMOUNT) + 210_000.0
assert totals["withdraw_limit_capacity_amount"] == expected_capacity, totals
assert totals["withdraw_limit_remaining_amount"] == expected_capacity - expected_withdraw, totals
assert totals["withdraw_limit_over_amount"] == 10_000.0, totals
assert round(totals["withdraw_limit_usage_percent"], 2) == round(expected_withdraw / expected_capacity * 100.0, 2), totals
assert totals["withdraw_limit_capacity_amount"] < (FILLER_COUNT + 2) * 200_000.0, totals

html = Dash.render_dashboard_html("test-token")
for marker in [
    "sharedWithdrawLimitUsage",
    "renderSharedWithdrawLimitUsage",
    "วงเงินจริงของบัญชีใช้ร่วม",
    "ใช้ร่วมข้ามบริษัท",
    "duplicate_capacity_amount",
]:
    assert marker in html, marker

print("ok: shared withdrawal account daily limit is counted once across companies")
