#!/usr/bin/env python3
"""Guard: side-menu function buttons map to the matching dashboard section and rendered JS stays clickable."""
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
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-side-menu-targets-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-side-menu-export-")))
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

menu_targets = set(re.findall(r'data-menu-target="([^"]+)"', html))
section_ids = re.findall(r'<section id="([^"]+)" class="[^"]*menu-section[^"]*"([^>]*)>', html)
missing_targets = [sid for sid, attrs in section_ids if 'data-always-visible="true"' not in attrs and sid not in menu_targets]
assert not missing_targets, f"menu-section ไม่มีปุ่มใน side menu: {missing_targets}"

for marker in [
    'data-menu-target="section-date-sender"',
    '>วันที่/ผู้ส่งรูป<',
    'data-menu-target="section-deposit-slips"',
    '>ฝาก/เติมมือ<',
    'data-menu-target="section-bank-review"',
    '>รีเช็คธนาคาร<',
    'id="section-deposit-slips"',
    'id="section-bank-review"',
    'depositCustomerSlips',
    'sourceBankReview',
    'closeSideMenuIfMobile',
]:
    assert marker in html, marker

# Each button title should reveal a section that contains that exact function, not a neighboring/bundled panel.
def section_html(section_id: str) -> str:
    match = re.search(rf'<section id="{re.escape(section_id)}"[^>]*>(.*?)</section>', html, re.S)
    assert match, section_id
    return match.group(1)

assert 'depositCustomerSlips' in section_html('section-deposit-slips')
assert 'depositCustomerSlips' not in section_html('limitSection')
assert 'sourceBankReview' in section_html('section-bank-review')
assert 'sourceBankReview' not in section_html('section-duplicates')
assert 'byDate' in section_html('section-date-sender') and 'bySender' in section_html('section-date-sender')

script_match = re.search(r'<script>(.*?)</script>', html, re.S)
assert script_match, "dashboard script missing"
script_path = Path(tempfile.mkdtemp(prefix="auditslip-js-check-")) / "dashboard.js"
script_path.write_text(script_match.group(1), encoding="utf-8")
if shutil.which("node"):
    result = subprocess.run(["node", "--check", str(script_path)], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr or result.stdout

print("ok: side menu function buttons map to real sections and rendered JS is valid")
