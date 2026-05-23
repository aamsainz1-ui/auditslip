#!/usr/bin/env python3
"""Guard: operator slip cards do not show internal slip IDs."""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-card-no-id-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-card-no-id-export-")))
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

def js_function(name: str) -> str:
    start = html.find(f"function {name}(")
    assert start >= 0, f"missing {name}"
    next_start = html.find("\nfunction ", start + 1)
    assert next_start > start, f"missing end for {name}"
    return html[start:next_start]

recent = js_function("recentCards")
dupe = js_function("renderDuplicatePairs")
review = js_function("sourceBankReviewCards")

# These are internal database identifiers. They may be used for image URLs/API calls,
# but they must not be printed as visible labels on operator cards.
for body, name in [(recent, "recentCards"), (dupe, "renderDuplicatePairs"), (review, "sourceBankReviewCards")]:
    for forbidden in ["id <code>", "ใบซ้ำ <code>", "ใบต้นฉบับ <code>", "จับคู่กับ ", "ซ้ำกับใบไหน"]:
        assert forbidden not in body, f"{name} still displays internal slip id via {forbidden!r}"

# Duplicate cards should still show useful evidence without exposing IDs.
for marker in ["ข้อมูลใบซ้ำ", "ข้อมูลต้นฉบับ", "ซ้ำกับใบต้นฉบับ", "ref"]:
    assert marker in dupe, marker

print("ok: dashboard slip cards hide internal slip IDs")
