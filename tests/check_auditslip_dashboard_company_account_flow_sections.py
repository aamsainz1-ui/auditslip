#!/usr/bin/env python3
"""Guard: company account daily rows are split into clear withdraw/deposit sections."""
from __future__ import annotations

import importlib.util
import os
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-account-flow-sections-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-account-flow-sections-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert spec is not None and spec.loader is not None
Dash = importlib.util.module_from_spec(spec)
spec.loader.exec_module(Dash)

html = Dash.render_dashboard_html("test-token")

required_markers = [
    "ฝั่งถอน · รายบัญชีตามวันที่",
    "ฝั่งฝาก/เติมมือ · รายบัญชีตามวันที่",
    'id="companyAccountDailyWithdraw"',
    'id="companyAccountDailyDeposit"',
    "companyAccountDailyWithdraw",
    "companyAccountDailyDeposit",
    "filter(r => r.flow_type === 'withdraw')",
    "filter(r => r.flow_type === 'deposit')",
]
for marker in required_markers:
    assert marker in html, marker

withdraw_pos = html.index("ฝั่งถอน · รายบัญชีตามวันที่")
deposit_pos = html.index("ฝั่งฝาก/เติมมือ · รายบัญชีตามวันที่")
assert withdraw_pos < deposit_pos, "withdraw section must appear before deposit/top-up so operators do not scroll past deposit rows"

# The old mixed container should not be the primary render target anymore.
assert 'id="companyAccountDaily"' not in html, "mixed all-flow container makes withdraw rows easy to bury under deposit rows"

script = re.search(r"<script>\n(.*?)\n</script>", html, re.S)
assert script, "dashboard script missing"
script_text = script.group(1)
assert "renderCompanyAccountDaily(accountDailyRows.filter(r => r.flow_type === 'withdraw'))" in script_text
assert "renderCompanyAccountDaily(accountDailyRows.filter(r => r.flow_type === 'deposit'))" in script_text

print("ok: company account daily UI separates withdraw and deposit sections")
