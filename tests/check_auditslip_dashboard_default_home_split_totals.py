#!/usr/bin/env python3
"""Guard: entry/refresh opens the combined dashboard home and top totals split withdraw/deposit."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "auditslip_dashboard.py"
spec = importlib.util.spec_from_file_location("auditslip_dashboard", MODULE)
assert spec and spec.loader
Dash = importlib.util.module_from_spec(spec)
spec.loader.exec_module(Dash)

html = Dash.render_dashboard_html("test-token")

# Browser entry/reload must land on the combined dashboard/home/top, not the last tool page such as reconcile.
assert "restoreActiveMenuSection" not in html
assert "ACTIVE_MENU_KEY" not in html
assert "window.history.scrollRestoration = 'manual'" in html
assert "showMenuSection('section-operator-home', {scroll:false, persist:false, syncHash:false})" in html
assert "refreshDashboardHome" in html
assert "load({home:true, scrollTop:true, smooth:false}); setInterval(() => load({lite:true}), 10000)" in html
assert "load({home:true, scrollTop:true, smooth:false, ignoreHash:true})" in html

# The top dashboard cards should not hide deposit+withdraw in one generic total.
for marker in [
    "ยอดถอนวันนี้/ช่วงที่เลือก",
    "withdrawAmount",
    "สลิปถอน",
    "withdrawCount",
    "ยอดฝาก/เติมมือวันนี้/ช่วงที่เลือก",
    "depositAmount",
    "สลิปฝาก/เติมมือ",
    "depositCount",
    "data.totals.withdraw_limit_amount",
    "data.totals.deposit_customer_amount",
]:
    assert marker in html, marker

print("ok: dashboard entry defaults to combined home and top totals split withdraw/deposit")
