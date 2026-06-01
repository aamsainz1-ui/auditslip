#!/usr/bin/env python3
"""Guard: operator dashboard keeps navigation short and slip cards show who/when evidence."""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-simple-menu-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-simple-menu-export-")))
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

# The side menu should start with a short quick menu, while lower-frequency tools are folded by group.
for marker in [
    "เมนูด่วน",
    "side-nav-quick",
    "side-menu-group",
    'data-menu-group="money"',
    'data-menu-group="slips"',
    'data-menu-group="system"',
    "openMenuGroupForTarget",
]:
    assert marker in html, marker

quick_match = re.search(r'<div class="side-nav side-nav-quick">(.*?)</div>\s*<details', html, re.S)
assert quick_match, "quick menu block missing"
quick_block = quick_match.group(1)
quick_targets = re.findall(r'data-menu-target="([^"]+)"', quick_block)
assert quick_targets == [
    "section-operator-home",
    "section-cross-company-accounts",
    "section-duplicates",
    "limitSection",
    "section-overview",
    "all",
], quick_targets

# Group sections are collapsed by default so the drawer does not become a long vertical list.
for group in ["money", "slips", "system"]:
    tag = re.search(rf'<details class="side-menu-group" data-menu-group="{group}"([^>]*)>', html)
    assert tag, group
    assert "open" not in tag.group(1), f"{group} should be collapsed by default"

# Slip cards should show operator evidence in plain Thai: who sent it and when.
for marker in [
    "เวลาในสลิป:",
    "ใครส่งรูป:",
    "ตรงกับบริษัทอื่น",
    "เวลา ",
    "cross_duplicate_matches",
]:
    assert marker in html, marker

print("ok: simple operator menu is compact and slip cards show who/when evidence")
