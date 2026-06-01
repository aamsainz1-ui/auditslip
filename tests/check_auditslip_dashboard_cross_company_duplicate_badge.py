#!/usr/bin/env python3
"""Guard: cross-company account slip cards flag exact duplicate fingerprints in other companies."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A,botB:BOT_TOKEN:บริษัท B"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-cross-dupe-badge-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-cross-dupe-badge-export-")))
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


def save(bot_key: str, slip_id: str, company: str, amount: float, ref: str, sender_name: str) -> None:
    bots[bot_key].save_slip({
        "id": slip_id,
        "bot_key": bot_key,
        "company_name": company,
        "chat_id": f"{bot_key}_WD",
        "chat_title": f"{company} ถอน",
        "message_id": 100 + len(slip_id),
        "file_id": f"FILE_{slip_id}",
        "sender_name": sender_name,
        "username": sender_name.lower().replace(" ", "_"),
        "status": "success",
        "slip_date_display": "24/05/26",
        "slip_date_iso": "2026-05-24",
        "slip_time": "10:00",
        "transferor_name": "MISTER SAME SOURCE",
        "recipient_name": company,
        "from_bank": "SCB",
        "from_account": "SHARED-ACC-456",
        "to_bank": "KBANK",
        "to_account": f"DEST-{bot_key}",
        "account_name": company,
        "amount": amount,
        "reference_no": ref,
    })


# Same amount + date + reference in two companies = exact duplicate fingerprint across companies.
save("botA", "A_DUP", "บริษัท A", 777.0, "DUP-REF-777", "Alice Sender")
save("botB", "B_DUP", "บริษัท B", 777.0, "DUP-REF-777", "Bob Sender")
# Same account, not the same slip. It should not be flagged as duplicate.
save("botA", "A_NORMAL", "บริษัท A", 123.0, "NORMAL-REF-123", "Alice Sender")

spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert spec and spec.loader
Dash = importlib.util.module_from_spec(spec)
sys.modules["auditslip_dashboard"] = Dash
spec.loader.exec_module(Dash)

snap = Dash.dashboard_snapshot(
    db_path,
    bot_key="__all__",
    flow_type="withdraw",
    scope="2026-05-24",
    slip_search="SHAREDACC456",
    account_search_mode="cross",
)
result = snap["cross_company_account_slip_search"]
assert result["is_cross_company"] is True, result
rows = result["rows"]
flagged = [r for r in rows if r.get("cross_duplicate_match_count")]
assert len(flagged) == 2, rows
for row in flagged:
    assert row["cross_duplicate_source_count"] == 2, row
    assert row["cross_duplicate_match_count"] == 1, row
    assert set(row["cross_duplicate_companies"]) == {"บริษัท A", "บริษัท B"}, row
    matches = row["cross_duplicate_matches"]
    assert len(matches) == 1, row
    assert matches[0]["company_name"] != row["company_name"], row
    assert set(matches[0]) == {"company_name", "bot_key", "message_id", "amount", "sender_display", "slip_date_text", "is_duplicate"}, matches[0]
    assert matches[0]["slip_date_text"], matches[0]

normal = [r for r in rows if r["reference"] == "NORMAL-REF-123"]
assert normal and normal[0].get("cross_duplicate_match_count", 0) == 0, rows

html = Dash.render_dashboard_html("test-token")
for marker in [
    "พบสลิปตรงกันในบริษัทอื่น",
    "cross_duplicate_matches",
    "cross_duplicate_match_count",
]:
    assert marker in html, marker

print("ok: cross-company slip cards expose exact duplicate matches in other companies")
