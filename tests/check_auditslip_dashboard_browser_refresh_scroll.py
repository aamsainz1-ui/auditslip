#!/usr/bin/env python3
"""Guard: browser refresh enters the combined dashboard home without restoring old tool pages."""
from __future__ import annotations

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = ROOT / "auditslip_dashboard.py"
spec = importlib.util.spec_from_file_location("auditslip_dashboard", MODULE)
assert spec and spec.loader
Dash = importlib.util.module_from_spec(spec)
spec.loader.exec_module(Dash)

html = Dash.render_dashboard_html("test-token")

# Browser/Safari reload should not restore a stale in-page position or old tool page.
assert "window.history.scrollRestoration = 'manual'" in html
assert "window.history.scrollRestoration = 'auto'" not in html

# Initial page boot and the explicit refresh button should return to top home; background polling must not scroll.
assert "refreshDashboardHome" in html
assert "topRefreshButton" in html
assert "load({home:true, scrollTop:true, smooth:false}); setInterval(() => load({lite:true}), 10000)" in html
assert "setInterval(() => load({lite:true}), 10000)" in html
assert "onclick=\"refreshDashboardHome()\"" in html

# Browser refresh/entry should always open the combined dashboard home instead of a stale tool page.
for removed_marker in [
    "ACTIVE_MENU_KEY",
    "safeStorageSet(ACTIVE_MENU_KEY",
    "function restoreActiveMenuSection",
    "restoreActiveMenuSection({scroll:false",
]:
    assert removed_marker not in html, removed_marker

for marker in [
    "showMenuSection(target, options={})",
    "if (options.scroll !== false && section) section.scrollIntoView",
    "showMenuSection('section-operator-home', {scroll:false, persist:false})",
]:
    assert marker in html, marker

print("ok: browser refresh enters dashboard home while explicit refresh can still scroll top")
