#!/usr/bin/env python3
"""Guard: cross-company UI blocks render hidden by default and unhide based on snapshot data.

Phase A1: dashboard must wrap the two cross-company panels in `accountCrossCompanyBlock`
and `crossCompanyAccountSlipSearchBlock`, both `hidden` by default. The JS `load()`
must read `is_cross_company` and `company_count` (from `cross_company_account_slip_search`)
and `account_cross_company.length` to toggle visibility.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-cc-conditional-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-cc-conditional-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert spec and spec.loader
Dash = importlib.util.module_from_spec(spec)
sys.modules["auditslip_dashboard"] = Dash
spec.loader.exec_module(Dash)

html = Dash.render_dashboard_html("test-token")

# Both wrapper blocks must exist with hidden attribute
assert 'id="accountCrossCompanyBlock"' in html, "missing accountCrossCompanyBlock wrapper"
assert 'id="crossCompanyAccountSlipSearchBlock"' in html, "missing crossCompanyAccountSlipSearchBlock wrapper"

# Both must be hidden by default. Spec: hidden attribute on the wrapper opening tag.
def _wrapper_has_hidden(wrapper_id: str) -> bool:
    needle = f'id="{wrapper_id}"'
    idx = html.find(needle)
    assert idx >= 0, f"wrapper {wrapper_id} not found"
    # Look at the tag-open window (assume wrapper opens on a single segment, scan back to '<')
    tag_start = html.rfind("<", 0, idx)
    tag_end = html.find(">", idx)
    assert tag_start >= 0 and tag_end > tag_start, f"could not parse tag for {wrapper_id}"
    tag = html[tag_start : tag_end + 1]
    return " hidden" in tag or tag.endswith(" hidden>") or '"hidden"' in tag or " hidden=" in tag or " hidden " in tag or tag.rstrip(">").endswith(" hidden")

assert _wrapper_has_hidden("accountCrossCompanyBlock"), "accountCrossCompanyBlock must be hidden by default"
assert _wrapper_has_hidden("crossCompanyAccountSlipSearchBlock"), "crossCompanyAccountSlipSearchBlock must be hidden by default"

# JS load() must read is_cross_company and company_count and account_cross_company to toggle
assert "is_cross_company" in html, "JS load must reference is_cross_company"
assert "company_count" in html, "JS load must reference company_count"
# The two block ids must be referenced in JS too (so load() can toggle them)
js_section = html[html.find("<script>") : html.rfind("</script>")]
assert "accountCrossCompanyBlock" in js_section, "JS must toggle accountCrossCompanyBlock"
assert "crossCompanyAccountSlipSearchBlock" in js_section, "JS must toggle crossCompanyAccountSlipSearchBlock"
assert "is_cross_company" in js_section, "JS must consult is_cross_company"
assert "company_count" in js_section, "JS must consult company_count"

print("ok: cross-company UI blocks render hidden by default and JS toggles them")
