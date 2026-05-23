#!/usr/bin/env python3
"""Guard: pending-approvals dashboard panel renders with section, filter, table, JS helpers, and badge."""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot1:BOT_TOKEN:บริษัท 1"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-pending-ui-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-pending-ui-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

html = Dash.render_dashboard_html("test-token")

# Section presence
assert 'id="section-pending"' in html, "section-pending missing"
assert 'class="sections menu-section"' in html, "section class wiring missing"
assert 'รออนุมัติ (Two-person approval)' in html, "section heading missing"

# Side-menu button + badge
assert 'data-menu-target="section-pending"' in html, "side menu button for section-pending missing"
assert 'id="pendingBadge"' in html, "pending badge element missing"
assert '>รออนุมัติ ' in html, "Thai 'รออนุมัติ' label missing in side menu"

# Filter + refresh + container
assert 'id="pendingStatusFilter"' in html, "status filter select missing"
assert 'id="pendingRefreshBtn"' in html, "refresh button missing"
assert 'id="pendingTableContainer"' in html, "table container missing"

# Filter options
for opt in ["pending", "approved", "executed", "rejected", "cancelled", "expired"]:
    assert f'value="{opt}"' in html, f"filter option {opt} missing"

# Table headers — Thai labels
for header in ["ID", "Action", "ผู้ขอ", "เวลาขอ", "expire", "status", "จัดการ"]:
    assert header in html, f"table header label missing: {header}"

# Action buttons + helper messages
for marker in ["อนุมัติ", "ปฏิเสธ", "ยกเลิก", "ห้าม self-approve"]:
    assert marker in html, f"helper/button label missing: {marker}"

# JS functions defined
for fn in [
    "function showToast(",
    "function loadPendingActions(",
    "function updatePendingBadge(",
    "function refreshPendingBadge(",
    "function approvePending(",
    "function rejectPending(",
    "function cancelPending(",
    "function executePending(",
    "function pendingActionEmoji(",
    "function pendingRowsTable(",
]:
    assert fn in html, f"JS helper missing: {fn}"

# Endpoint wiring
assert "/api/pending" in html, "/api/pending endpoint missing in JS"
assert "/api/pending/approve" in html, "/api/pending/approve endpoint missing in JS"
assert "/api/pending/reject" in html, "/api/pending/reject endpoint missing in JS"
assert "/api/pending/cancel" in html, "/api/pending/cancel endpoint missing in JS"

# Polling + hook into load()
assert "setInterval(refreshPendingBadge, 30000)" in html, "30s pending badge polling missing"
assert "loadPendingActions({scrollTop:false})" in html, "loadPendingActions hook missing"

# Toast host
assert 'id="pendingToastHost"' in html, "toast host element missing"

# Extract <script> blocks and verify with node --check
script_blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
assert script_blocks, "no <script> blocks found"
combined_js = "\n;\n".join(script_blocks)
script_path = Path(tempfile.mkdtemp(prefix="auditslip-pending-js-")) / "dashboard.js"
script_path.write_text(combined_js, encoding="utf-8")
if shutil.which("node"):
    result = subprocess.run(["node", "--check", str(script_path)], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr or result.stdout

# Sanity: section-pending block actually contains the table container and filter
match = re.search(r'<section id="section-pending"[^>]*>(.*?)</section>', html, re.S)
assert match, "section-pending block not found"
inner = match.group(1)
assert 'id="pendingStatusFilter"' in inner, "filter not inside section-pending"
assert 'id="pendingTableContainer"' in inner, "table container not inside section-pending"

print("ok: pending approvals UI section, filter, table, JS helpers, and badge polling rendered")
