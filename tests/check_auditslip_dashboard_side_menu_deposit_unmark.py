#!/usr/bin/env python3
"""Guard: side menu, deposit/เติมมือ flow without limits, and duplicate unmark button wiring."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["BOT_TOKEN"] = "TEST_TOKEN"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot3:BOT_TOKEN:บริษัท 3"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-side-deposit-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(Path(tempfile.mkdtemp(prefix="auditslip-side-deposit-export-")))
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TEST_TOKEN", db_path=db_path, dry_run=True, bot_key="bot3", company_name="บริษัท 3")
bot.init_db()
base = {
    "bot_key": "bot3",
    "company_name": "บริษัท 3",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:00",
    "transferor_name": "ลูกค้า",
    "recipient_name": "บริษัท 3",
    "from_bank": "SCB",
    "to_bank": "KBANK",
    "amount": 100.0,
    "reference_no": "REF-BASE",
}
bot.save_slip({**base, "id": "DEP_TM", "chat_id": "CHAT_DEPOSIT", "chat_title": "บริษัท 3 เติมมือ", "message_id": 21, "file_id": "FILE_DEP", "amount": 300.0, "reference_no": "REF-DEP"})
bot.save_slip({**base, "id": "WD1", "chat_id": "CHAT_WITHDRAW", "chat_title": "บริษัท 3 ถอน", "message_id": 11, "file_id": "FILE_WD", "amount": 1000.0, "reference_no": "REF-WD"})
bot.save_slip({**base, "id": "ORIG", "chat_id": "CHAT_WITHDRAW", "chat_title": "บริษัท 3 ถอน", "message_id": 12, "file_id": "FILE_ORIG", "amount": 500.0, "reference_no": "REF-ORIG"})
bot.save_slip({**base, "id": "DUP", "chat_id": "CHAT_WITHDRAW", "chat_title": "บริษัท 3 ถอน", "message_id": 13, "file_id": "FILE_DUP", "amount": 500.0, "reference_no": "REF-ORIG", "is_duplicate": 1, "duplicate_of": "ORIG"})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)

snap_dep = Dash.dashboard_snapshot(db_path, bot_key="bot3", flow_type="deposit", scope="open")
assert snap_dep["flow_type"] == "deposit", snap_dep
assert snap_dep["totals"]["selected_success_count"] == 1, snap_dep["totals"]
assert snap_dep["totals"]["selected_success_amount"] == 300.0, snap_dep["totals"]
assert {r["chat_id"] for r in snap_dep["recent"]} == {"CHAT_DEPOSIT"}, snap_dep["recent"]
assert snap_dep.get("limit_check_enabled") is False, snap_dep
assert snap_dep["by_account_day"] == [] and snap_dep["by_transferor"] == [], snap_dep

chats = {r["chat_id"]: r["flow_type"] for r in snap_dep["chats"]}
assert chats["CHAT_DEPOSIT"] == "deposit", chats
assert chats["CHAT_WITHDRAW"] == "withdraw", chats

result = Dash.unmark_duplicate_slip(db_path, "DUP", "__all__")
assert result["ok"] is True, result
snap_wd = Dash.dashboard_snapshot(db_path, bot_key="bot3", flow_type="withdraw", scope="open", slip_filter="duplicate")
assert "DUP" not in [r.get("duplicate_id") for r in snap_wd["duplicate_pairs"]], snap_wd["duplicate_pairs"]

html = Dash.render_dashboard_html("test-token")
for marker in [
    "sideMenu",
    "sideCompanies",
    "เมนูฟังก์ชั่น",
    "submenu บริษัท",
    "renderSideCompanies",
    "section-duplicates",
    "limitSection",
    "limit_check_enabled",
    "กลุ่มฝาก/เติมมือ ไม่ต้องเช็กวงเงิน",
    "data-dupe-id",
    "unmarkDuplicate(this.dataset.dupeId)",
    "sideMenuToggle",
    "toggleSideMenu",
    "applySideMenuState",
    "auditslip.sideMenuCollapsed",
    "side-collapsed",
    "showMenuSection",
    "showAllMenuSections",
    "data-menu-target",
    "menu-section",
]:
    assert marker in html, marker
assert "onclick=\"unmarkDuplicate(" not in html, "duplicate button must not break HTML attribute quotes"

print("ok: side menu + เติมมือ deposit no-limit + duplicate unmark wiring")
