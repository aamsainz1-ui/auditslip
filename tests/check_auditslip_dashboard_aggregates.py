#!/usr/bin/env python3
"""Guard: dashboard shows scoped totals by transferor, bank, and Telegram sender."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-dash-agg-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-dash-agg-export-")))
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True)
bot.init_db()

def slip(idx: int, *, transferor: str, sender: str, issuer_bank: str, from_bank: str, to_bank: str, amount: float, from_account: str = "", duplicate: int = 0) -> None:
    bot.save_slip({
        "id": f"S{idx}",
        "chat_id": "CHAT1",
        "chat_title": "Audit Room",
        "message_id": idx,
        "file_id": f"FILE{idx}",
        "sender_name": sender,
        "status": "success",
        "slip_date_display": "22/05/26",
        "slip_date_iso": "2026-05-22",
        "slip_time": f"10:{idx:02d}",
        "transferor_name": transferor,
        "issuer_bank": issuer_bank,
        "from_bank": from_bank,
        "from_account": from_account,
        "to_bank": to_bank,
        "amount": amount,
        "fee": 0,
        "confidence": 0.99,
        "is_duplicate": duplicate,
    })

slip(1, transferor="คุณเอ", sender="Uploader One", issuer_bank="KBank", from_bank="KBank", from_account="111-xxx-222", to_bank="SCB", amount=100.0)
slip(2, transferor="คุณเอ", sender="Uploader Two", issuer_bank="กสิกรไทย", from_bank="กสิกรไทย", from_account="111-xxx-222", to_bank="ไทยพาณิชย์", amount=250.0)
slip(3, transferor="คุณบี", sender="Uploader One", issuer_bank="ไทยพาณิชย์", from_bank="SCB", from_account="333-xxx-444", to_bank="KBank", amount=75.0)
# Same transferor account with a missing source bank should merge into the known-bank account row,
# not show as a separate daily/account-limit line.
slip(5, transferor="คุณเอ", sender="Uploader Two", issuer_bank="", from_bank="", from_account="111-xxx-222", to_bank="ไทยพาณิชย์", amount=10.0)
slip(4, transferor="คุณเอ", sender="Uploader One", issuer_bank="KBank", from_bank="KBank", from_account="111-xxx-222", to_bank="SCB", amount=999.0, duplicate=1)

# another chat must not leak into selected-chat aggregates
bot.save_slip({
    "id": "OTHER",
    "chat_id": "CHAT2",
    "chat_title": "Other Room",
    "message_id": 99,
    "file_id": "FILE99",
    "sender_name": "Other Uploader",
    "status": "success",
    "slip_date_iso": "2026-05-22",
    "slip_time": "12:00",
    "transferor_name": "คนอื่น",
    "issuer_bank": "OtherBank",
    "from_bank": "OtherBank",
    "to_bank": "OtherDest",
    "amount": 5000.0,
})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snapshot = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]), chat_id="CHAT1", scope="open")
assert snapshot["selected_chat_id"] == "CHAT1", snapshot
assert snapshot["scope"] == "open", snapshot
assert snapshot["totals"]["open_success_count"] == 4, snapshot
assert snapshot["totals"]["open_success_amount"] == 435.0, snapshot
assert snapshot["totals"]["selected_duplicate_count"] == 1, snapshot
assert snapshot["totals"]["selected_duplicate_amount"] == 999.0, snapshot
recent_by_id = {row["id"]: row for row in snapshot["recent"]}
assert recent_by_id["S1"]["slip_date_text"] == "22/05/26 10:01", recent_by_id["S1"]

by_transferor = {row["name"]: row for row in snapshot["by_transferor"]}
assert by_transferor["คุณเอ (KBANK)"]["count"] == 3, by_transferor
assert by_transferor["คุณเอ (KBANK)"]["amount"] == 360.0, by_transferor
assert by_transferor["คุณเอ (KBANK)"]["account"] == "111-xxx-222", by_transferor
assert by_transferor["คุณเอ (KBANK)"]["limit_amount"] == 0.0, by_transferor
assert by_transferor["คุณบี (SCB)"]["amount"] == 75.0, by_transferor
assert by_transferor["คุณบี (SCB)"]["limit_amount"] == 200000.0, by_transferor
Dash.save_account_limit(Path(os.environ["AUDITSLIP_DB"]), "CHAT1", by_transferor["คุณเอ (KBANK)"]["limit_key"], "คุณเอ", "KBANK", "111-xxx-222", 300.0)
snapshot = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]), chat_id="CHAT1", scope="open")
by_transferor = {row["name"]: row for row in snapshot["by_transferor"]}
assert by_transferor["คุณเอ (KBANK)"]["limit_amount"] == 300.0, by_transferor
assert by_transferor["คุณเอ (KBANK)"]["remaining_amount"] == -60.0, by_transferor
assert by_transferor["คุณเอ (KBANK)"]["over_limit"] is True, by_transferor
by_account_day = {row["name"]: row for row in snapshot["by_account_day"]}
assert by_account_day["คุณเอ (KBANK)"]["count"] == 3, by_account_day
assert by_account_day["คุณเอ (KBANK)"]["amount"] == 360.0, by_account_day

by_from_bank = {row["name"]: row for row in snapshot["by_from_bank"]}
assert by_from_bank["KBANK"]["amount"] == 350.0, by_from_bank
assert by_from_bank["SCB"]["amount"] == 75.0, by_from_bank

assert "by_issuer_bank" not in snapshot, snapshot.keys()

by_sender = {row["name"]: row for row in snapshot["by_sender"]}
assert by_sender["Uploader One"]["count"] == 2, by_sender
assert by_sender["Uploader One"]["amount"] == 175.0, by_sender
assert by_sender["Uploader Two"]["amount"] == 260.0, by_sender

html = Dash.render_dashboard_html("test-token")
for marker in ["byTransferor", "byFromBank", "bySender", "ผู้โอน", "ธนาคารต้นทาง", "ผู้ส่งรูป", "duplicateCount", "recentCards", "slip-card", "สลิปซ้ำ", "ตั้งวงเงินบัญชี", "transferorLimitTable"]:
    assert marker in html, marker
for removed in ["byIssuerBank", "ธนาคารบนสลิป"]:
    assert removed not in html, removed
print("ok: dashboard scoped aggregates by transferor/bank/sender")
