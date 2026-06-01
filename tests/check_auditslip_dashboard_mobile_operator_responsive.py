#!/usr/bin/env python3
"""Guard: mobile operator mode has bottom nav and deep-link hash scroll is not overridden."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-mobile-responsive-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-mobile-responsive-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=Path(os.environ["AUDITSLIP_DB"]), dry_run=True)
bot.init_db()

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)
html = Dash.render_dashboard_html("test-token")

required_markers = [
    # Mobile-first operator navigation: the most-used sections must be one tap away.
    "id=\"mobileBottomNav\"",
    "aria-label=\"เมนูด่วนมือถือ\"",
    "data-mobile-target=\"section-operator-home\"",
    "data-mobile-target=\"section-cross-company-accounts\"",
    "data-mobile-target=\"section-duplicates\"",
    "data-mobile-target=\"limitSection\"",
    "class=\"mobile-bottom-nav\"",
    "bottom:calc(8px + env(safe-area-inset-bottom))",
    "padding-bottom:calc(82px + env(safe-area-inset-bottom))",
    "@media (max-width: 780px)",
    ".mobile-bottom-nav button",
    # Deep-link hash should open/scroll the requested section, not snap back to the home/top cards.
    "function applyInitialHashSection",
    "let initialHashApplied = false",
    "showMenuSection(initialHashTarget, {scroll:false, syncHash:false})",
    "scrollMenuSectionIntoView(initialHashTarget, false)",
    "function scheduleHashTargetScroll",
    "requestAnimationFrame(() => scrollMenuSectionIntoView(target, smooth))",
    "setTimeout(() => scrollMenuSectionIntoView(target, smooth), 80)",
    "setTimeout(() => scheduleHashTargetScroll(initialHashTarget, false), 260)",
    "if (!initialHashApplied && options && options.scrollTop)",
    # Mobile card polish: no horizontal overflow, better slip cards/tap targets on narrow screens.
    "scroll-margin-top:86px",
    ".mobile-action-label",
    ".slip-card .top",
    ".side-menu-item, .mobile-bottom-nav button",
]

for marker in required_markers:
    assert marker in html, marker

print("ok: mobile operator responsive/deep-link markers")
