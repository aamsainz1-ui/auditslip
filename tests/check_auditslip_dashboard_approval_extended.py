#!/usr/bin/env python3
"""Guard: two-person approval workflow covers company.account and reconcile.run.

Account-limit changes are operational settings and should save directly from the
UI/API without creating pending approvals. High-risk actions still use pending.
For each pending action in this test:
  - create_pending_action stores the row with status='pending'
  - self-approval (requester == approver) is blocked
  - second actor approval flips status to 'approved'
  - APPROVAL_REQUIRED_ACTIONS contains the action name
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
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-approval-ext-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-approval-ext-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"
# Suppress real network alerts during this test.
os.environ["AUDITSLIP_ALERT_ON_MUTATION"] = "0"

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

actor_a = "fpAAAAAAAAAA"
actor_b = "fpBBBBBBBBBB"

# Sanity: account.limit is direct-save, while high-risk dotted action names still require approval.
assert "account.limit" not in Dash.APPROVAL_REQUIRED_ACTIONS, Dash.APPROVAL_REQUIRED_ACTIONS
assert "company.account" in Dash.APPROVAL_REQUIRED_ACTIONS, Dash.APPROVAL_REQUIRED_ACTIONS
assert "reconcile.run" in Dash.APPROVAL_REQUIRED_ACTIONS, Dash.APPROVAL_REQUIRED_ACTIONS
# Old approval actions still present.
assert "slip.delete" in Dash.APPROVAL_REQUIRED_ACTIONS
assert "period.close" in Dash.APPROVAL_REQUIRED_ACTIONS


def assert_full_approval_cycle(action: str, payload: dict) -> None:
    # Step 1: requester creates pending
    pending_id = Dash.create_pending_action(
        db_path,
        action=action,
        payload=payload,
        requested_by=actor_a,
        request_id=f"req-{action}-001",
    )
    assert isinstance(pending_id, int) and pending_id > 0
    row = Dash.load_pending_action(db_path, pending_id)
    assert row["status"] == "pending", row
    assert row["requested_by"] == actor_a, row
    assert row["action"] == action, row

    # Step 2: self-approval blocked
    self_ap = Dash.approve_pending_action(db_path, pending_id, actor_a)
    assert self_ap.get("ok") is False, self_ap
    assert "self-approval" in (self_ap.get("error") or ""), self_ap
    assert Dash.load_pending_action(db_path, pending_id)["status"] == "pending"

    # Step 3: second actor approves
    ap = Dash.approve_pending_action(db_path, pending_id, actor_b)
    assert ap.get("ok") is True, ap
    row = Dash.load_pending_action(db_path, pending_id)
    assert row["status"] == "approved", row
    assert row["approved_by"] == actor_b, row

    # Step 4: stored payload survives round-trip
    stored = Dash.pending_action_payload(row)
    for k, v in payload.items():
        assert stored.get(k) == v, (action, k, stored)

    # Step 5: cannot approve twice
    again = Dash.approve_pending_action(db_path, pending_id, actor_b)
    assert again.get("ok") is False, again


assert_full_approval_cycle(
    "company.account",
    {
        "bot_key": "bot3",
        "chat_id": "CHAT_B",
        "company_name": "บริษัท 3",
        "bank": "KBANK",
        "account_no": "1112223334",
        "account_name": "บริษัท 3 จำกัด",
        "daily_limit": 100000,
    },
)

assert_full_approval_cycle(
    "reconcile.run",
    {
        "chat_id": "CHAT_C",
        "bot_key": "bot3",
        "flow_type": "all",
        "scope": "today",
        "excel_path": "/tmp/auditslip-recon-pretend.xlsx",
    },
)

print("ok: approval workflow covers company.account/reconcile.run and excludes direct account limits")
