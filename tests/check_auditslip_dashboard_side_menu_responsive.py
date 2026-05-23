#!/usr/bin/env python3
"""Guard: side menu behaves as responsive drawer on phones and collapsed rail on desktop."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-side-responsive-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-side-responsive-export-")))
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

for marker in [
    "id=\"sideScrim\"",
    "id=\"sideMenuClose\"",
    "onclick=\"closeSideMenu()\"",
    "body.side-open .side-scrim",
    "body.side-open .side-menu",
    "@media (max-width: 780px)",
    "position:fixed",
    "transform:translateX(-105%)",
    "isMobileSideMenu",
    "openSideMenu",
    "closeSideMenu",
    "window.matchMedia('(max-width: 780px)')",
    "aria-expanded",
    "sideMenuToggle",
    "enhanceResponsiveTables",
    "td::before",
    "attr(data-label)",
    "@media (max-width: 640px)",
    "scrollDashboardTop",
    "window.history.scrollRestoration = 'manual'",
    "refreshDashboardHome",
    "showMenuSection('section-operator-home', {scroll:false, persist:false})",
    "load({home:true, scrollTop:true, smooth:false})",
    "setInterval(() => load({lite:true}), 10000)",
]:
    assert marker in html, marker

for removed_marker in ["ACTIVE_MENU_KEY", "restoreActiveMenuSection({scroll:false})"]:
    assert removed_marker not in html, removed_marker

print("ok: responsive side menu drawer markers")
