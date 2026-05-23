#!/usr/bin/env python3
"""Guard: dashboard_snapshot accepts account_search_mode to scope or cross-search.

Phase A1: when account_search_mode='scoped' (default), cross_company_account_slip_search
must come back empty (the cross-company search is skipped). When 'cross', the scoped
account_slip_search.rows must come back empty (the scoped search is skipped). This is
the surgical separation that backs the new UI toggle between scoped vs cross search.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A,botB:BOT_TOKEN:บริษัท B"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-search-mode-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-search-mode-export-")))
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
for b in bots.values():
    b.init_db()


def save(bot_key: str, slip_id: str, company: str, chat_id: str, title: str, amount: float, from_account: str, ref: str) -> None:
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
        "slip_date_display": "22/05/26",
        "slip_date_iso": "2026-05-22",
        "slip_time": "10:00",
        "transferor_name": f"ลูกค้า {company}",
        "recipient_name": company,
        "from_bank": "SCB",
        "from_account": from_account,
        "to_bank": "KBANK",
        "to_account": f"DEST-{bot_key}",
        "account_name": company,
        "amount": amount,
        "reference_no": ref,
    })


# Two companies sharing the same source account — cross-company search should find rows in both.
save("botA", "A1", "บริษัท A", "A_WD", "บริษัท A ถอน", 100.0, "SHARED-ACC-789", "RA01")
save("botB", "B1", "บริษัท B", "B_WD", "บริษัท B ถอน", 200.0, "SHARED-ACC-789", "RB01")

spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert spec and spec.loader
Dash = importlib.util.module_from_spec(spec)
sys.modules["auditslip_dashboard"] = Dash
spec.loader.exec_module(Dash)

# Mode 'scoped' — cross-company search result must be empty rows; scoped account_slip_search keeps rows.
snap_scoped = Dash.dashboard_snapshot(
    db_path,
    bot_key="botA",
    flow_type="withdraw",
    scope="2026-05-22",
    slip_search="SHAREDACC789",
    account_search_mode="scoped",
)
assert snap_scoped["cross_company_account_slip_search"]["rows"] == [], snap_scoped["cross_company_account_slip_search"]
assert snap_scoped["cross_company_account_slip_search"].get("is_cross_company", False) is False, snap_scoped["cross_company_account_slip_search"]
assert snap_scoped["account_slip_search"]["rows"], snap_scoped["account_slip_search"]

# Mode 'cross' — scoped account_slip_search rows must be empty; cross result populated.
snap_cross = Dash.dashboard_snapshot(
    db_path,
    bot_key="botA",
    flow_type="withdraw",
    scope="2026-05-22",
    slip_search="SHAREDACC789",
    account_search_mode="cross",
)
assert snap_cross["account_slip_search"]["rows"] == [], snap_cross["account_slip_search"]
assert snap_cross["cross_company_account_slip_search"]["count"] == 2, snap_cross["cross_company_account_slip_search"]
assert snap_cross["cross_company_account_slip_search"]["is_cross_company"] is True, snap_cross["cross_company_account_slip_search"]

# Default (no kwarg) preserves legacy behavior: both panels populated.
snap_default = Dash.dashboard_snapshot(
    db_path,
    bot_key="botA",
    flow_type="withdraw",
    scope="2026-05-22",
    slip_search="SHAREDACC789",
)
assert snap_default["account_slip_search"]["rows"], snap_default["account_slip_search"]
assert snap_default["cross_company_account_slip_search"]["rows"], snap_default["cross_company_account_slip_search"]

print("ok: dashboard_snapshot honors account_search_mode (scoped vs cross)")
