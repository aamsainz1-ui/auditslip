#!/usr/bin/env python3
"""Guard: recheck/exception queues count the whole scope, not a fixed visible shortlist."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TOKEN_RECHECK"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botreview:BOT_TOKEN:บริษัท Review"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-auto-recheck-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-auto-recheck-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TOKEN_RECHECK", db_path=db_path, dry_run=True, bot_key="botreview", company_name="บริษัท Review")
bot.init_db()

base = {
    "bot_key": "botreview",
    "company_name": "บริษัท Review",
    "chat_id": "CHAT_REVIEW",
    "chat_title": "บริษัท Review ถอน",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "recipient_name": "บริษัท Review",
    "to_bank": "SCB",
    "to_account": "222",
    "confidence": 0.95,
}

# More than the old visible cap of 40; every item should be counted as needing bank recheck.
for i in range(45):
    bot.save_slip({
        **base,
        "id": f"MISS_BANK_{i:02d}",
        "message_id": 1000 + i,
        "file_id": f"FILE_MISS_BANK_{i:02d}",
        "slip_time": f"10:{i % 60:02d}",
        "transferor_name": f"ลูกค้า {i:02d}",
        "from_bank": "",
        "from_account": f"111-{i:03d}",
        "amount": float(100 + i),
        "reference_no": f"REF-MISS-{i:02d}",
    })

# These are financially complete slips: the source side is known, only destination metadata is blank.
# They must not inflate the operator exception/recheck queue.
bot.save_slip({**base, "id": "KNOWN_SOURCE_MISSING_DEST", "message_id": 1900, "file_id": "FILE_KNOWN_SOURCE_MISSING_DEST", "from_bank": "SCB", "from_account": "111-KNOWN", "to_bank": "", "to_account": "222", "transferor_name": "ลูกค้าปกติ", "amount": 321.0, "reference_no": "REF-KNOWN-SOURCE"})
bot.save_slip({**base, "id": "ISSUER_SOURCE_MISSING_DEST", "message_id": 1901, "file_id": "FILE_ISSUER_SOURCE_MISSING_DEST", "issuer_bank": "ไทยพาณิชย์", "from_bank": "", "from_account": "111-ISSUER", "to_bank": "", "to_account": "222", "transferor_name": "ลูกค้าปกติ 2", "amount": 654.0, "reference_no": "REF-ISSUER-SOURCE"})

# Add a duplicate and an OCR issue so the exception summary proves multiple automatic categories.
bot.save_slip({**base, "id": "ORIG_OK", "message_id": 2000, "file_id": "FILE_ORIG", "from_bank": "KBANK", "from_account": "111-OK", "transferor_name": "ต้นฉบับ", "amount": 999.0, "reference_no": "REF-ORIG"})
bot.save_slip({**base, "id": "DUP_OK", "message_id": 2001, "file_id": "FILE_DUP", "from_bank": "KBANK", "from_account": "111-OK", "transferor_name": "ต้นฉบับ", "amount": 999.0, "reference_no": "REF-ORIG", "is_duplicate": 1, "duplicate_of": "ORIG_OK"})
bot.save_slip({**base, "id": "ISSUE_ONE", "message_id": 3000, "file_id": "FILE_ISSUE", "status": "unclear", "error": "missing amount", "amount": 0.0, "reference_no": "REF-ISSUE"})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snapshot = Dash.dashboard_snapshot(db_path, chat_id="CHAT_REVIEW", bot_key="botreview", scope="open")
assert snapshot["totals"]["source_bank_review_count"] == 45, snapshot["totals"]
assert len(snapshot["source_bank_review"]) == 40, "visible card list can remain capped, but count must be complete"
summary = snapshot["exception_summary"]
assert summary["bank_review_count"] == 45, summary
assert summary["duplicate_count"] == 1, summary
assert summary["issue_count"] == 1, summary
assert summary["total_count"] >= 47, summary

calls = []
def fake_bank_recheck(db_path_arg, slip_id, apply=True):
    calls.append(slip_id)
    if slip_id == "MISS_BANK_10":
        raise RuntimeError("simulated 429 rate limit")
    return {"ok": True, "id": slip_id}

Dash.openai_bank_double_check_slip = fake_bank_recheck
bulk = Dash.openai_bank_recheck_scope(db_path, chat_id="CHAT_REVIEW", bot_key="botreview", scope="open", flow_type="withdraw", apply=True)
assert bulk["total_count"] == 45, bulk
assert bulk["ok_count"] == 44, bulk
assert bulk["fail_count"] == 1, bulk
assert bulk["errors"] and bulk["errors"][0]["id"] == "MISS_BANK_10", bulk
assert set(calls) == {f"MISS_BANK_{i:02d}" for i in range(45)}, calls
assert calls.count("MISS_BANK_10") == 3, calls

html = Dash.render_dashboard_html("test-token")
for marker in [
    "currentSnapshot.exception_summary",
    "openaiBankRecheckAllScope",
    "/api/bank-review/openai-all",
    "exception_summary",
]:
    assert marker in html, marker
assert ".slice(0, 8)" not in html
assert "ทั้งหมดที่แสดง" not in html

print("ok: recheck/exception queues count all scoped items and bulk bank recheck is scope-based")
