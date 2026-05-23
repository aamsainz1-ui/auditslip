#!/usr/bin/env python3
"""Guard: backend reconciliation forces company + deposit/withdraw scope before upload."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "botA:BOT_TOKEN:บริษัท A,botB:BOT_TOKEN:บริษัท B"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-reconcile-company-flow-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-reconcile-company-flow-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

html = Dash.render_dashboard_html("test-token")
source_text = (ROOT / "auditslip_dashboard.py").read_text(encoding="utf-8")
for marker in [
    "reconcileCompanyFilter",
    "reconcileFlowFilter",
    "reconcileScopePreview",
    "เลือกบริษัทก่อน",
    "เลือกยอดฝาก/ถอน",
    "อัปโหลด Excel ของบริษัทนี้",
    "ไฟล์นี้จะถูกเทียบเฉพาะบริษัทและฝาก/ถอนที่เลือก",
]:
    assert marker in html, marker

start = html.index("async function runReconcile")
end = html.index("async function load", start)
run_block = html[start:end]
for marker in [
    "const bot = document.getElementById('reconcileCompanyFilter').value",
    "const flow = document.getElementById('reconcileFlowFilter').value",
    "bot === '__all__'",
    "flow !== 'deposit' && flow !== 'withdraw'",
    "form.append('chat_id', '')",
    "JSON.stringify({chat_id:'', bot_key:bot, flow_type:flow",
    "เลือกบริษัทและฝาก/ถอนก่อนอัปโหลดไฟล์หลังบ้าน",
]:
    assert marker in run_block, marker

for marker in [
    "function updateReconcileScopePreview",
    "reconcileCompanyFilter.innerHTML",
    "reconcileFlowFilter.value",
]:
    assert marker in source_text, marker

print("ok: reconcile upload requires explicit company and deposit/withdraw scope")
