#!/usr/bin/env python3
"""Guard: dated all-company export must not navigate the dashboard to a blank download page."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TOKEN1"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot1:BOT_TOKEN:บริษัท 1"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-export-frame-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-export-frame-out-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert spec and spec.loader
Dash = importlib.util.module_from_spec(spec)
sys.modules["auditslip_dashboard"] = Dash
spec.loader.exec_module(Dash)

html = Dash.render_dashboard_html("test-token")

# Dated ZIP/XLSX downloads can render a blank page in mobile WebViews if the anchor
# navigates the main dashboard tab. Keep the main app alive by targeting a hidden frame.
assert 'id="exportDownloadFrame"' in html and 'name="exportDownloadFrame"' in html, "missing hidden export iframe"
assert 'id="excel"' in html and 'target="exportDownloadFrame"' in html, "export link must target hidden frame"
assert "window.location = buildExcelUrl" not in html
assert "location.href = buildExcelUrl" not in html
assert "return true;" in html, "export should still allow the iframe navigation/download"

print("ok: dated company export downloads without replacing dashboard page")
