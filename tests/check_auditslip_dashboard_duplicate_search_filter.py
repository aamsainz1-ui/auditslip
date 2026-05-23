#!/usr/bin/env python3
"""Guard: dashboard search can find duplicate pairs against previously captured slips."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-duplicate-search-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-duplicate-search-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True, bot_key="bot1", company_name="บริษัท 1")
bot.init_db()

base = {
    "bot_key": "bot1",
    "company_name": "บริษัท 1",
    "chat_id": "CHAT1",
    "chat_title": "Audit Room",
    "sender_name": "Uploader Alpha",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:00",
    "transferor_name": "คุณเอ",
    "recipient_name": "ร้านค้า",
    "from_bank": "SCB",
    "from_account": "111-xxx-222",
    "to_bank": "KBANK",
    "to_account": "333-xxx-444",
    "amount": 100.0,
    "reference_no": "REF-ORIGINAL-100",
    "seq": "SEQ100",
    "confidence": 0.99,
}

bot.save_slip({**base, "id": "ORIG-100", "message_id": 1, "file_id": "FILE_ORIG"})
bot.save_slip({**base, "id": "DUP-100", "message_id": 2, "file_id": "FILE_DUP", "is_duplicate": 1, "duplicate_of": "ORIG-100"})
bot.save_slip({
    **base,
    "id": "OTHER-200",
    "message_id": 3,
    "file_id": "FILE_OTHER",
    "slip_time": "11:00",
    "transferor_name": "คุณบี",
    "amount": 200.0,
    "reference_no": "REF-OTHER-200",
    "seq": "SEQ200",
})

# Same duplicate id text in another bot must not leak into bot1 search results.
bot2 = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True, bot_key="bot2", company_name="บริษัท 2")
bot2.init_db()
bot2.save_slip({**base, "bot_key": "bot2", "company_name": "บริษัท 2", "id": "ORIG-100-BOT2", "message_id": 20, "file_id": "FILE_BOT2"})
bot2.save_slip({**base, "bot_key": "bot2", "company_name": "บริษัท 2", "id": "DUP-100-BOT2", "message_id": 21, "file_id": "FILE_BOT2_DUP", "is_duplicate": 1, "duplicate_of": "ORIG-100-BOT2"})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

def ids_for(query: str):
    snap = Dash.dashboard_snapshot(Path(os.environ["AUDITSLIP_DB"]), chat_id="CHAT1", bot_key="bot1", scope="open", slip_filter="duplicate", slip_search=query)
    return [row["duplicate_id"] for row in snap["duplicate_pairs"]], [row["id"] for row in snap["recent"]], snap

pairs, recent, snap = ids_for("ORIG-100")
assert pairs == ["DUP-100"], snap["duplicate_pairs"]
assert recent == ["DUP-100"], snap["recent"]
assert snap["slip_search"] == "ORIG-100", snap

pairs, recent, snap = ids_for("DUP-100")
assert pairs == ["DUP-100"], snap["duplicate_pairs"]
assert recent == ["DUP-100"], snap["recent"]

pairs, recent, snap = ids_for("REF-ORIGINAL-100")
assert pairs == ["DUP-100"], snap["duplicate_pairs"]
assert recent == ["DUP-100"], snap["recent"]

pairs, recent, snap = ids_for("คุณเอ")
assert pairs == ["DUP-100"], snap["duplicate_pairs"]
assert recent == ["DUP-100"], snap["recent"]

pairs, recent, snap = ids_for("REF-OTHER-200")
assert pairs == [] and recent == [], snap

html = Dash.render_dashboard_html("test-token")
for marker in ["slipSearch", "ค้นหาสลิป", "ค้นหาสลิปซ้ำ", "clearSlipSearch", "slip_search"]:
    assert marker in html, marker

print("ok: duplicate search filter matches previous captured slips")
