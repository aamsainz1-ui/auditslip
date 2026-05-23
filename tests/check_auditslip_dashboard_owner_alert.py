#!/usr/bin/env python3
"""Guard: record_endpoint_mutation fires a single send_owner_alert for each high-risk action,
skips low-risk actions, and respects AUDITSLIP_ALERT_ON_MUTATION=0 to disable.

Strategy: monkeypatch Dash.send_owner_alert with a recording stub, then call
record_endpoint_mutation against an in-memory test DB.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot3:BOT_TOKEN:บริษัท 3"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-owner-alert-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-owner-alert-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"
# Telegram env vars set so send_owner_alert WOULD attempt a network call -- but we
# monkeypatch the function, so no network is actually touched.
os.environ["AUDITSLIP_WATCHDOG_BOT_TOKEN"] = "fake-token"
os.environ["AUDITSLIP_WATCHDOG_ALERT_CHAT_ID"] = "999"
# Make sure the gate is on by default.
os.environ.pop("AUDITSLIP_ALERT_ON_MUTATION", None)

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="bot3", company_name="บริษัท 3")
bot.init_db()

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

# Capture send_owner_alert calls without touching the network.
calls: list[dict] = []


def fake_alert(message: str, action: str = "", request_id: str = "") -> None:
    calls.append({"message": message, "action": action, "request_id": request_id})


Dash.send_owner_alert = fake_alert  # monkeypatch

HIGH_RISK = [
    "delete",
    "close",
    "clear",
    "account_limit",
    "company_account",
    "token.create",
    "token.revoke",
]

# Case 1: each high-risk action fires exactly one alert with the expected format
for idx, action in enumerate(HIGH_RISK):
    calls.clear()
    req_id = f"req{idx:08x}"
    Dash.record_endpoint_mutation(
        db_path,
        action,
        actor="fpAAAAAAAAAA",
        request_id=req_id,
        payload={"k": "v"},
        result_status="ok",
        result_summary=f"summary-for-{action}",
    )
    assert len(calls) == 1, f"{action}: expected 1 alert, got {len(calls)}: {calls}"
    msg = calls[0]["message"]
    assert "🚨 Auditslip mutation:" in msg, msg
    assert f"{action}" in msg, msg
    # actor short prefix: first 8 chars of fp
    assert "fpAAAAAA" in msg, msg
    assert f"req={req_id}" in msg, msg
    assert "result=ok" in msg, msg
    assert f"summary-for-{action}" in msg, msg
    assert calls[0]["action"] == action
    assert calls[0]["request_id"] == req_id

# Case 2: reprocess is low-risk -> no alert
calls.clear()
Dash.record_endpoint_mutation(
    db_path,
    "reprocess",
    actor="fpAAAAAAAAAA",
    request_id="req-rp",
    payload={"id": "S1"},
    result_status="ok",
    result_summary="reprocessed",
)
assert calls == [], f"reprocess should not alert, got {calls}"

# Case 3: unmark_dup is low-risk -> no alert
calls.clear()
Dash.record_endpoint_mutation(
    db_path,
    "unmark_dup",
    actor="fpAAAAAAAAAA",
    request_id="req-ud",
    payload={"id": "S1"},
    result_status="ok",
    result_summary="unmarked",
)
assert calls == [], f"unmark_dup should not alert, got {calls}"

# Case 4: env AUDITSLIP_ALERT_ON_MUTATION=0 disables the alert even for high-risk actions
os.environ["AUDITSLIP_ALERT_ON_MUTATION"] = "0"
try:
    calls.clear()
    Dash.record_endpoint_mutation(
        db_path,
        "delete",
        actor="fpAAAAAAAAAA",
        request_id="req-disabled",
        payload={"id": "S1"},
        result_status="ok",
        result_summary="deleted",
    )
    assert calls == [], f"AUDITSLIP_ALERT_ON_MUTATION=0 should suppress alert, got {calls}"
finally:
    os.environ.pop("AUDITSLIP_ALERT_ON_MUTATION", None)

# Case 5: failure inside send_owner_alert must not raise out of record_endpoint_mutation
def boom_alert(message: str, action: str = "", request_id: str = "") -> None:
    raise RuntimeError("network down")


Dash.send_owner_alert = boom_alert
# Should not raise
Dash.record_endpoint_mutation(
    db_path,
    "delete",
    actor="fpAAAAAAAAAA",
    request_id="req-boom",
    payload={"id": "S1"},
    result_status="ok",
    result_summary="deleted",
)

# Case 6: result_summary is truncated at 200 chars
Dash.send_owner_alert = fake_alert
calls.clear()
long_summary = "x" * 500
Dash.record_endpoint_mutation(
    db_path,
    "close",
    actor="fpAAAAAAAAAA",
    request_id="req-long",
    payload={},
    result_status="ok",
    result_summary=long_summary,
)
assert len(calls) == 1
msg = calls[0]["message"]
# The portion after the header line should be at most 200 'x' chars.
trailing = msg.split("\n", 1)[1] if "\n" in msg else ""
assert len(trailing) == 200, f"expected 200-char trailing snip, got {len(trailing)}"
assert trailing == "x" * 200

print("ok: owner alert fires for high-risk mutations, skips low-risk, respects disable flag")
