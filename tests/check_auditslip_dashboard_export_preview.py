#!/usr/bin/env python3
"""Guard: export preview/dry-run is read-only and does not create XLSX/ZIP files."""
from __future__ import annotations

import email.message
import importlib.util
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = Path(tempfile.mkdtemp(prefix="auditslip-export-preview-out-"))
os.environ["BOT_TOKEN"] = "TOKEN1"
os.environ["AUDITSLIP_TELEGRAM_BOTS"] = "bot1:BOT_TOKEN:บริษัท 1"
os.environ["AUDITSLIP_DB"] = str(Path(tempfile.mkdtemp(prefix="auditslip-export-preview-")) / "auditslip.db")
os.environ["AUDITSLIP_HOME"] = str(ROOT)
os.environ["AUDITSLIP_EXPORT_DIR"] = str(EXPORT_DIR)
os.environ["AUDITSLIP_DASHBOARD_TOKEN"] = "test-token"
os.environ["GEMINI_API_KEY"] = "gemini-test-key"
os.environ["OPENAI_API_KEY"] = "openai-test-key"

bot_spec = importlib.util.spec_from_file_location("auditslip_bot", ROOT / "auditslip_bot.py")
assert bot_spec and bot_spec.loader
bot_mod = importlib.util.module_from_spec(bot_spec)
sys.modules["auditslip_bot"] = bot_mod
bot_spec.loader.exec_module(bot_mod)

db_path = Path(os.environ["AUDITSLIP_DB"])
bot = bot_mod.AuditslipBot(token="TOKEN1", db_path=db_path, dry_run=True, bot_key="bot1", company_name="บริษัท 1")
bot.init_db()
base = {
    "bot_key": "bot1",
    "company_name": "บริษัท 1",
    "chat_id": "CHAT1",
    "chat_title": "บริษัท 1 ถอน",
    "sender_name": "Uploader",
    "status": "success",
    "slip_date_display": "22/05/26",
    "slip_date_iso": "2026-05-22",
    "slip_time": "10:00",
    "transferor_name": "ลูกค้า",
    "recipient_name": "ร้านค้า",
    "from_bank": "KBANK",
    "to_bank": "SCB",
    "amount": 100.0,
    "reference_no": "R-BASE",
}
bot.save_slip({**base, "id": "W1", "message_id": 1, "file_id": "FW1", "amount": 100.0, "reference_no": "RW1"})
bot.save_slip({**base, "id": "W_DUP", "message_id": 2, "file_id": "FD1", "amount": 100.0, "reference_no": "RDUP", "is_duplicate": 1, "duplicate_of": "W1"})
bot.save_slip({**base, "id": "D1", "chat_title": "บริษัท 1 ฝาก", "message_id": 3, "file_id": "FD2", "amount": 300.0, "reference_no": "RD1"})

dash_spec = importlib.util.spec_from_file_location("auditslip_dashboard", ROOT / "auditslip_dashboard.py")
assert dash_spec and dash_spec.loader
Dash = importlib.util.module_from_spec(dash_spec)
sys.modules["auditslip_dashboard"] = Dash
dash_spec.loader.exec_module(Dash)


class _FakeHandler(Dash.DashboardHandler):
    def __init__(self, path: str) -> None:
        self.client_address = ("127.0.0.1", 0)
        self.request_version = "HTTP/1.1"
        self.requestline = f"GET {path} HTTP/1.1"
        self.command = "GET"
        self.path = path
        self.rfile = io.BytesIO()
        self.wfile = io.BytesIO()
        self.headers = email.message.Message()
        self._status_code: int = 0
        self._sent_headers: List[Tuple[str, str]] = []

    def send_response(self, code: int, message: str | None = None) -> None:  # type: ignore[override]
        self._status_code = int(code)

    def send_header(self, keyword: str, value: str) -> None:  # type: ignore[override]
        self._sent_headers.append((keyword, value))

    def end_headers(self) -> None:  # type: ignore[override]
        return

    def log_message(self, fmt: str, *args: Any) -> None:  # type: ignore[override]
        return

    def json_body(self) -> Dict[str, Any]:
        return json.loads(self.wfile.getvalue().decode("utf-8") or "{}")


def get_json(path: str) -> Dict[str, Any]:
    before = sorted(EXPORT_DIR.glob("*"))
    h = _FakeHandler(path)
    h.do_GET()
    after = sorted(EXPORT_DIR.glob("*"))
    assert h._status_code == 200, (h._status_code, h.wfile.getvalue()[:300])
    assert before == after == [], f"preview/dry-run created files: before={before}, after={after}"
    data = h.json_body()
    assert data.get("ok") is True, data
    assert data.get("dry_run") is True, data
    return data

preview = get_json("/api/export/preview?bot_key=bot1&scope=all&flow_type=withdraw")
assert preview["format"] == "xlsx", preview
assert preview["mime"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", preview
assert preview["scope"]["bot_key"] == "bot1", preview
assert preview["scope"]["flow_type"] == "withdraw", preview
assert preview["rows"]["selected"] == 2, preview  # includes duplicate evidence row in workbook selection
assert preview["rows"]["counted"] == 1, preview
assert preview["rows"]["duplicates"] == 1, preview
for sheet in ["SummaryByCompany", "SummaryByTransferor", "DailySummary", "Slips", "WithdrawSlips", "DepositSlips", "DuplicateSlips"]:
    assert sheet in preview["sheets"], preview
assert preview["sheets"]["WithdrawSlips"] == 1, preview
assert preview["sheets"]["DepositSlips"] == 0, preview
assert preview["sheets"]["DuplicateSlips"] == 1, preview
assert preview["filename"].endswith(".xlsx"), preview

# Same read-only preview must be available on the existing export path for production smoke checks.
dry_run = get_json("/api/export?dry_run=1&bot_key=bot1&scope=all&flow_type=withdraw")
assert dry_run["filename"] == preview["filename"], (preview, dry_run)
assert dry_run["sheets"] == preview["sheets"], (preview, dry_run)

print("ok: dashboard export preview/dry-run is read-only and reports sheets/row counts")
