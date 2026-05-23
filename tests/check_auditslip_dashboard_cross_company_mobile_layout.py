#!/usr/bin/env python3
"""Guard: cross-company account usage renders as readable stacked cards, not a squeezed mobile table."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-cross-company-layout-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-cross-company-layout-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

html = Dash.render_dashboard_html("test-token")
required_markers = [
    "cross-company-list",
    "cross-company-card",
    "cross-company-company",
    "cross-company-day-row",
    "แยกตามบริษัท",
    "ยอดรายวันรวม",
    "รวมบัญชีนี้",
]
missing = [marker for marker in required_markers if marker not in html]
assert not missing, missing

# The cross-company renderer should no longer use the generic responsive table layout
# that squeezed the company/day detail into a narrow right column on iPhone.
start = html.index("function renderAccountCrossCompany")
end = html.index("function renderCompanyOverview", start)
renderer = html[start:end]
assert "<table" not in renderer, renderer[:500]
assert "grid-template-columns:minmax(104px,42%) 1fr" in html  # generic tables still exist for other sections

print("ok: cross-company account usage has mobile stacked-card layout")
