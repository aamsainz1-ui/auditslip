#!/usr/bin/env python3
"""Guard: product-ready dashboard shell, operator defaults, and auth-token hardening."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-product-shell-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-product-shell-export-")))
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
source = (ROOT / "auditslip_dashboard.py").read_text(encoding="utf-8")

# Product shell: daily operator home and mobile top actions must be first-class, not hidden only in side menu.
for marker in [
    "id=\"mobileTopActions\"",
    "id=\"topRefreshButton\"",
    "id=\"activeScopeChip\"",
    "id=\"lastUpdatedLabel\"",
    "id=\"section-operator-home\"",
    "renderOperatorHome",
    "renderExceptionQueue",
    "งานวันนี้",
    "รายการที่ต้องจัดการ",
    "ตั้งค่า/Admin",
    "data-admin-only",
    "toggleAdminMode",
    "isSingleChatSelected",
    "closeOpenPeriodGuard",
]:
    assert marker in html, marker

# Operator-facing labels should be Thai while keeping machine values intact.
for marker in [
    '<option value="open">รอบเปิด</option>',
    '<option value="today" selected>วันนี้</option>',
    '<option value="all">ทั้งหมด</option>',
    "บริษัท · ฝาก/ถอน · รอบ",
]:
    assert marker in html, marker

# Token must not be rendered into HTML/JS or appended to every client-side URL.
assert "test-token" not in html
assert "dashboardToken" not in html
assert "p.set('token'" not in html
assert 'token_qs = ' not in source

# Security headers and cookie/query bootstrap helpers must exist in the handler.
for marker in [
    "Content-Security-Policy",
    "X-Frame-Options",
    "Referrer-Policy",
    "X-Content-Type-Options",
    "Cache-Control",
    "cookie_attrs",
    "X-Auditslip-Action",
    "csrf_authorized",
]:
    assert marker in source, marker

print("ok: product shell and dashboard token hardening markers")
