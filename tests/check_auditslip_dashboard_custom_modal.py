#!/usr/bin/env python3
"""Guard: dashboard destructive/long actions use in-page modal instead of native browser alert/confirm."""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-modal-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-modal-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"

spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert spec and spec.loader
Dash = importlib.util.module_from_spec(spec)
sys.modules["auditslip_dashboard"] = Dash
spec.loader.exec_module(Dash)

html = Dash.render_dashboard_html("test-token")
for marker in [
    "id=\"dashboardModal\"",
    "id=\"dashboardModalInput\"",
    "dashboardNotify",
    "dashboardConfirm",
    "dashboardInput",
    "await dashboardConfirm",
    "await dashboardNotify",
    "await dashboardInput",
    "modal-title",
    "modal-primary",
    "modal-cancel",
    "modal-input",
]:
    assert marker in html, marker

match = re.search(r"<script>\n(.*?)\n</script>", html, re.S)
assert match, "rendered dashboard script not found"
script = match.group(1)
for forbidden in ["alert(", "confirm(", "prompt(", "window.alert", "window.confirm", "window.prompt"]:
    assert forbidden not in script, f"native browser dialog still present: {forbidden}"

print("ok: dashboard uses custom modal for alerts/confirms/input prompts")
