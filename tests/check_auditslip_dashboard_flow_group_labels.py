#!/usr/bin/env python3
"""Guard: deposit/withdraw/group labels are consistent across Python + rendered dashboard."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot1:BOT_TOKEN:บริษัท 1"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-flow-labels-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-flow-labels-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

assert Dash.normalize_flow_type("เติมมือ") == "deposit"
assert Dash.normalize_flow_type("เติมเงิน") == "deposit"
assert Dash.normalize_flow_type("ฝาก/เติมมือ") == "deposit"
assert Dash.flow_label("deposit") == "ฝาก/เติมมือ"
assert Dash.flow_label("withdraw") == "ถอน"
assert Dash.flow_label("all") == "รวมทุกกลุ่ม"

html = Dash.render_dashboard_html("test-token")
for marker in [
    "ทุกกลุ่มฝาก/เติมมือ",
    "[กลุ่มฝาก/เติมมือ]",
    "[กลุ่มถอน]",
    "รวมทุกกลุ่ม",
    "flowName(value)",
    "ฝาก/เติมมือ",
]:
    assert marker in html, marker

print("ok: flow/group labels are consistent for deposit/top-up and withdraw")
